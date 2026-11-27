"""Authenticated, constrained WebSocket transport for Bridge calls."""

import asyncio
import base64
import contextlib
import hashlib
import logging
import re
import uuid
from urllib.parse import urlencode, urlsplit, urlunsplit

import aiohttp
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials
from open_webui.utils.machines import machine_id_of
from open_webui.config import BYPASS_ADMIN_ACCESS_CONTROL, DEFAULT_REALTIME_CALL_PROMPT_TEMPLATE
from open_webui.env import AIOHTTP_CLIENT_SESSION_SSL, BYPASS_MODEL_ACCESS_CONTROL, ENABLE_FORWARD_USER_INFO_HEADERS
from open_webui.models.chats import Chats
from open_webui.models.config import Config
from open_webui.models.models import Models, ModelVoice
from open_webui.utils.access_control import has_permission
from open_webui.utils.auth import get_verified_user_by_token
from open_webui.utils.headers import get_microsoft_entra_id_access_token, include_user_info_headers
from open_webui.utils.json_codec import JSONCodec
from open_webui.utils.models import check_model_access, get_all_models
from open_webui.utils.session_pool import get_session
from open_webui.utils.voice_avatar import avatar_animation_tools

router = APIRouter()
log = logging.getLogger(__name__)

# Messages are bounded before JSON parsing. Audio appends contain at most one second.
MAX_EVENT_BYTES = 512 * 1024
CALL_STATUSES = {
    'working': 'I am working on your request.',
    'approval': 'Please review the approval or question in chat. I will wait for you there.',
    'deferred': 'Please complete the required settings or confirmation in chat, then try again.',
}

DIRECT_REALTIME_CALL_PROMPT = (
    'You are the assistant in this live voice call, speaking directly with the user. '
    'Answer questions and requests directly in brief, natural spoken sentences without internal monologue, '
    'thinking tags, markdown formatting, or unsupported tool calls. '
    'If an essential choice or detail is genuinely unclear or missing, call the ask_user tool with concise questions '
    'and crisp spoken options rather than guessing.'
)

AVATAR_CALL_INSTRUCTIONS = """
Your avatar is your visible presence in this call. Use play_animation directly for available gestures.
Treat gestures as your actions and converse naturally without narrating their implementation. Ground acknowledgments in the tool's actual result.
"""

_STT_LANG_RE = re.compile(r'^[a-z]{2,8}(?:[-_][a-z0-9]{2,8})?$')

ASK_USER_REALTIME_TOOL = {
    'type': 'function',
    'name': 'ask_user',
    'description': (
        'Ask the user 1 to 3 concise clarifying questions with crisp options that can be answered by voice.'
    ),
    'parameters': {
        'type': 'object',
        'properties': {
            'questions': {
                'type': 'array',
                'minItems': 1,
                'maxItems': 3,
                'items': {
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'string'},
                        'header': {'type': 'string'},
                        'question': {'type': 'string'},
                        'options': {
                            'type': 'array',
                            'items': {
                                'type': 'object',
                                'properties': {
                                    'label': {'type': 'string'},
                                    'description': {'type': 'string'},
                                },
                                'required': ['label'],
                            },
                        },
                        'allow_other': {'type': 'boolean'},
                    },
                    'required': ['question'],
                },
            },
            'allow_other': {'type': 'boolean'},
            'timeout_ms': {'type': 'integer'},
        },
        'required': ['questions'],
    },
}


class CallProtocol:
    """Connection-local IDs and the client command allowlist; never forwards arbitrary session settings."""

    def __init__(self, gestures=(), enable_ask_user=False, transcription_model=None):
        self.gesture_names = {gesture.name for gesture in gestures}
        self.animation_tools = avatar_animation_tools(gestures) if gestures else []
        self.enable_ask_user = bool(enable_ask_user)
        self.transcription_model = transcription_model or 'whisper-1'
        self.animation_calls = {}
        self.animation_seen = set()
        self.animation_responses = set()
        self.ask_user_calls = set()
        self.pending_ask_user_call_id = None
        self.response_metadata = {}
        self.finished_responses = set()
        self.transcripts = set()
        self.requested = set()
        self.functions = set()
        self.results = {}
        self.audio = {}
        self.responses = set()
        self.context_revision = 0
        self.synced_prefix_items = []  # [(prefix_item_id, role, content), ...]

    def observe(self, event):
        kind = event.get('type')
        if kind in {
            'conversation.item.input_audio_transcription.completed',
            'conversation.item.input_audio_transcription.failed',
        }:
            if kind.endswith('.completed') and event.get('transcript', '').strip():
                self.transcripts.add(event['item_id'])
            else:
                # Rejected turns must leave the provider's history as well as the chat.
                return {'type': 'conversation.item.delete', 'item_id': event['item_id']}
        elif kind == 'response.created':
            self.responses.add(event['response']['id'])
            self.response_metadata[event['response']['id']] = event['response'].get('metadata') or {}
        elif kind == 'response.done':
            self.finished_responses.add(event['response']['id'])
        elif kind == 'ask_user.requested':
            if isinstance(event.get('call_id'), str):
                self.ask_user_calls.add(event['call_id'])
                self.pending_ask_user_call_id = event['call_id']
        elif kind in {'ask_user.resolved', 'ask_user.cancelled'}:
            if event.get('call_id') == self.pending_ask_user_call_id:
                self.pending_ask_user_call_id = None
        elif kind == 'response.output_item.done':
            item = event.get('item', {})
            if item.get('type') == 'function_call' and item.get('status') == 'completed':
                if item.get('name') == 'ask_user' and isinstance(item.get('call_id'), str):
                    self.ask_user_calls.add(item['call_id'])
                    self.pending_ask_user_call_id = item['call_id']
                    return
                elif item.get('name') == 'play_animation':
                    if item['call_id'] in self.animation_seen:
                        return
                    if len(self.animation_seen) >= 4096:
                        raise ValueError('Call limit reached. Start a new call.')
                    try:
                        args = JSONCodec.loads(item.get('arguments', ''))
                        valid = isinstance(args, dict) and set(args) == {'name'} and args['name'] in self.gesture_names
                    except (ValueError, TypeError):
                        valid = False
                    event['animation_valid'] = bool(valid)
                    self.animation_seen.add(item['call_id'])
                    self.animation_calls[item['call_id']] = (event['response_id'], valid)
                    self.animation_responses.add(event['response_id'])
                    return
                if item.get('name') != 'generate_chat_completion':
                    raise ValueError('Unexpected voice function')
                args = JSONCodec.loads(item.get('arguments', ''))
                if not isinstance(args, dict) or set(args) != {'request'} or not isinstance(args['request'], str):
                    raise ValueError('Invalid voice function arguments')
                if not 0 < len(args['request'].strip()) <= 32000:
                    raise ValueError('Invalid voice function request')
                self.functions.add(item['call_id'])
        elif kind == 'response.output_audio.delta':
            key = (event['item_id'], event['content_index'])
            pcm = base64.b64decode(event['delta'], validate=True)
            if len(pcm) % 2:
                raise ValueError('Invalid provider PCM')
            self.audio[key] = self.audio.get(key, 0) + len(pcm) // 2
        if max(len(self.transcripts), len(self.responses), len(self.audio), len(self.functions)) > 4096:
            raise ValueError('Call limit reached. Start a new call.')

    def command(self, event):
        if not isinstance(event, dict):
            raise ValueError('Invalid call command')
        kind = event.get('type')
        if kind == 'input_audio_buffer.append' and set(event) == {'type', 'audio'}:
            pcm = base64.b64decode(event['audio'], validate=True)
            if not pcm or len(pcm) > 48000 or len(pcm) % 2:
                raise ValueError('Invalid microphone audio')
            return event
        if kind in {'input_audio_buffer.commit', 'input_audio_buffer.clear'} and set(event) == {'type'}:
            return event
        if kind == 'response.cancel' and set(event) == {'type', 'response_id'}:
            if event['response_id'] not in self.responses:
                raise ValueError('Unknown response')
            return event
        if kind == 'conversation.item.truncate' and set(event) == {'type', 'item_id', 'content_index', 'audio_end_ms'}:
            samples = self.audio.get((event['item_id'], event['content_index']))
            end = event['audio_end_ms']
            if samples is None or type(end) is not int or not 0 <= end <= samples * 1000 // 24000:
                raise ValueError('Invalid playback position')
            return event
        if kind == 'bridge.context' and set(event) == {'type', 'messages'}:
            messages = event['messages']
            if not isinstance(messages, list) or len(messages) > 100:
                raise ValueError('Invalid call history')
            size = 0
            canonical_prefix = []
            for idx, message in enumerate(messages):
                if (
                    not isinstance(message, dict)
                    or not {'role', 'content'}.issubset(message)
                    or not set(message).issubset({'id', 'role', 'content'})
                ):
                    raise ValueError('Invalid history message')
                role, content = message['role'], message['content']
                if role not in {'user', 'assistant'} or not isinstance(content, str) or len(content) > 32000:
                    raise ValueError('Invalid history message')
                clean_content = content.strip()
                if not clean_content:
                    continue
                size += len(clean_content)
                digest = hashlib.sha256(f'{idx}:{role}:{clean_content}'.encode('utf-8')).hexdigest()[:8]
                canonical_prefix.append((f'prefix_{idx}_{digest}', role, clean_content))
            if size > 64000:
                raise ValueError('Call history is too large')
            if canonical_prefix == self.synced_prefix_items:
                return []
            items = [
                {'type': 'conversation.item.delete', 'item_id': old_id}
                for old_id, _old_role, _old_content in self.synced_prefix_items
                if old_id not in {pid for pid, _, _ in canonical_prefix}
            ]
            existing_ids = {old_id for old_id, _, _ in self.synced_prefix_items}
            for prefix_id, role, clean_content in canonical_prefix:
                if prefix_id in existing_ids:
                    continue
                items.append(
                    {
                        'type': 'conversation.item.create',
                        'item': {
                            'id': prefix_id,
                            'type': 'message',
                            'role': role,
                            'content': [{'type': 'input_text', 'text': clean_content}],
                        },
                    }
                )
            self.synced_prefix_items = canonical_prefix
            self.context_revision += 1
            return items
        if kind == 'bridge.stt_language' and set(event) == {'type', 'language'}:
            raw_lang = str(event.get('language') or '').strip().lower()
            if not raw_lang or raw_lang in {'auto', 'detect', 'automatic'}:
                tx = {'model': self.transcription_model, 'language': 'auto'}
            elif _STT_LANG_RE.fullmatch(raw_lang):
                tx = {'model': self.transcription_model, 'language': raw_lang}
            else:
                raise ValueError('Invalid STT language code')
            return {
                'type': 'session.update',
                'session': {'audio': {'input': {'transcription': tx}}},
            }
        if kind == 'bridge.ask_user.submit' and set(event) == {'type', 'call_id', 'status', 'answers'}:
            call_id = event.get('call_id')
            if not isinstance(call_id, str) or call_id not in self.ask_user_calls:
                raise ValueError('Unknown ask_user call')
            if event['status'] not in {'answered', 'cancelled'} or not isinstance(event['answers'], dict):
                raise ValueError('Invalid ask_user payload')
            return [
                {
                    'type': 'conversation.item.create',
                    'item': {
                        'type': 'function_call_output',
                        'call_id': call_id,
                        'output': JSONCodec.dumps({'status': event['status'], 'answers': event['answers']}),
                    },
                },
                {'type': 'response.create', 'response': {'metadata': {'ask_user_call_id': call_id}}},
            ]
        if kind == 'bridge.ask_user.cancel' and set(event) == {'type', 'call_id'}:
            call_id = event.get('call_id')
            if not isinstance(call_id, str) or call_id not in self.ask_user_calls:
                raise ValueError('Unknown ask_user call')
            return {'type': 'ask_user.cancel', 'call_id': call_id}
        if kind == 'bridge.animation.result' and set(event) == {'type', 'call_id', 'status'}:
            pending = self.animation_calls.pop(event['call_id'], None)
            if pending is None or event['status'] not in {'started', 'busy', 'unavailable', 'cancelled'}:
                raise ValueError('Invalid animation result')
            status = event['status'] if pending[1] else 'unavailable'
            return {
                'type': 'conversation.item.create',
                'item': {
                    'type': 'function_call_output',
                    'call_id': event['call_id'],
                    'output': JSONCodec.dumps(
                        {
                            'status': status,
                            'effect': {
                                'started': 'The requested gesture has started and is visible to the user.',
                                'busy': (
                                    'An earlier gesture is still being performed. This additional request was skipped '
                                    'to avoid overlap. This is not a playback failure and does not cancel the earlier gesture.'
                                ),
                                'unavailable': (
                                    'This request could not start. This result does not change the outcome '
                                    'of any earlier gesture that already started.'
                                ),
                                'cancelled': 'This request was skipped because its response was interrupted.',
                            }[status],
                        }
                    ),
                },
            }
        if kind == 'bridge.animation.respond' and set(event) == {'type', 'response_id'}:
            response_id = event['response_id']
            if (
                response_id not in self.animation_responses
                or response_id not in self.finished_responses
                or any(p[0] == response_id for p in self.animation_calls.values())
            ):
                raise ValueError('Animation response is not ready')
            self.animation_responses.remove(response_id)
            metadata = {
                k: v
                for k, v in self.response_metadata.get(response_id, {}).items()
                if k in {'input_item_id', 'call_id'}
            }
            # A gesture cannot cause a chain of gesture-only replies.
            return {
                'type': 'response.create',
                'response': {
                    'metadata': metadata,
                    'tools': [],
                    'tool_choice': 'none',
                },
            }
        if kind == 'bridge.result' and set(event) == {'type', 'call_id', 'status', 'answer'}:
            if event['call_id'] not in self.functions:
                raise ValueError('Unknown or resolved function call')
            if event['status'] not in {'completed', 'failed', 'cancelled', 'deferred'}:
                raise ValueError('Invalid function result')
            if not isinstance(event['answer'], str) or len(event['answer']) > 100000:
                raise ValueError('Invalid function answer')
            self.functions.remove(event['call_id'])
            self.results[event['call_id']] = event['status']
            return {
                'type': 'conversation.item.create',
                'item': {
                    'type': 'function_call_output',
                    'call_id': event['call_id'],
                    'output': JSONCodec.dumps({'status': event['status'], 'answer': event['answer']}),
                },
            }
        if kind == 'bridge.respond':
            if set(event) == {'type', 'item_id'}:
                item_id = event['item_id']
                if item_id not in self.transcripts or item_id in self.requested:
                    raise ValueError('Unknown or already answered input')
                self.requested.add(item_id)
                resp_meta = {'input_item_id': item_id}
                if self.pending_ask_user_call_id:
                    resp_meta['ask_user_call_id'] = self.pending_ask_user_call_id
                return {'type': 'response.create', 'response': {'metadata': resp_meta}}
            if set(event) == {'type', 'call_id'}:
                # Results can be spoken once; the client cannot inject response instructions.
                call_id = event['call_id']
                if call_id in self.functions or f'result:{call_id}' not in self.requested:
                    raise ValueError('Function result is not ready')
                self.requested.remove(f'result:{call_id}')
                failed = self.results.pop(call_id) == 'failed'
                return {
                    'type': 'response.create',
                    'response': {
                        'tools': [] if failed else self.animation_tools,
                        'tool_choice': 'auto' if self.animation_tools and not failed else 'none',
                        **(
                            {
                                'instructions': (
                                    'Briefly tell the user the request failed, in their language. No retry is running. '
                                    'Tell them they can ask you to retry, then stop. Do not claim work is continuing '
                                    'or invent a cause.'
                                )
                            }
                            if failed
                            else {}
                        ),
                        'metadata': {'call_id': call_id},
                    },
                }
        if kind == 'bridge.status' and set(event) == {'type', 'status'} and event['status'] in CALL_STATUSES:
            return {
                'type': 'response.create',
                'response': {
                    'conversation': 'none',
                    'input': [],
                    'tools': [],
                    'tool_choice': 'none',
                    'instructions': f"Say this briefly in the user's language: {CALL_STATUSES[event['status']]}",
                    'metadata': {'status': event['status']},
                },
            }
        raise ValueError('Unsupported call command')


async def _get_realtime_connection(config: dict) -> tuple[str, dict[str, str]]:
    provider = config.get('audio.realtime.provider', 'openai')
    auth_type = config.get('audio.realtime.auth_type', 'api_key')
    if provider not in {'openai', 'azure'} or auth_type not in {'api_key', 'microsoft_entra_id'}:
        raise ValueError('Unsupported Realtime provider or authentication method')
    if provider != 'azure' and auth_type == 'microsoft_entra_id':
        raise ValueError('Microsoft Entra ID requires the Azure OpenAI Realtime provider')

    try:
        url = urlsplit(config.get('audio.realtime.openai.api_base_url') or '')
        valid_url = (
            url.scheme in {'http', 'https'}
            and url.hostname
            and not (url.username or url.password or url.query or url.fragment)
        )
        url.port  # Validate a supplied port before opening the connection.
    except ValueError:
        valid_url = False
    if not valid_url:
        raise ValueError('Invalid Realtime provider URL')
    model = config.get('audio.realtime.model')
    if not model:
        raise ValueError('Configure the Realtime model')
    ws_url = urlunsplit(
        (
            'wss' if url.scheme == 'https' else 'ws',
            url.netloc,
            url.path.rstrip('/') + '/realtime',
            urlencode({'model': model}),
            '',
        )
    )

    if auth_type == 'microsoft_entra_id':
        try:
            token = await asyncio.to_thread(get_microsoft_entra_id_access_token)
        except Exception:
            raise ValueError('Unable to obtain a Microsoft Entra ID token for Realtime calls') from None
        if not token:
            raise ValueError('Unable to obtain a Microsoft Entra ID token for Realtime calls')
        headers = {'Authorization': f'Bearer {token}'}
    else:
        key = config.get('audio.realtime.openai.api_key')
        if not key:
            raise ValueError('Configure the Realtime API key')
        headers = {'api-key': key} if provider == 'azure' else {'Authorization': f'Bearer {key}'}
    return ws_url, headers


@router.websocket('/realtime')
async def realtime_call(ws: WebSocket):
    await ws.accept()
    upstream = None
    tasks = []
    user = None
    try:
        async with asyncio.timeout(10):
            raw = await ws.receive_text()
        if len(raw) > 8192:
            raise ValueError('Invalid authentication message')
        auth = JSONCodec.loads(raw)
        if not isinstance(auth, dict) or auth.get('type') != 'auth' or not isinstance(auth.get('token'), str):
            raise ValueError('Authentication required')
        token = auth['token']
        redis = getattr(ws.app.state, 'redis', None)
        user = await get_verified_user_by_token(token, redis)
        if not user:
            raise ValueError('Authentication expired or invalid')
        config = await Config.get_many(
            'audio.realtime.enabled',
            'audio.realtime.provider',
            'audio.realtime.auth_type',
            'audio.realtime.openai.api_base_url',
            'audio.realtime.openai.api_key',
            'audio.realtime.model',
            'audio.realtime.voice',
            'audio.realtime.transcription_model',
            'audio.realtime.input_params',
            'audio.realtime.prompt_template',
            'user.permissions',
        )
        if not config.get('audio.realtime.enabled'):
            raise ValueError('Realtime calls are disabled')
        if user.role != 'admin' and not await has_permission(user.id, 'chat.call', config.get('user.permissions', {})):
            raise ValueError('Call permission denied')
        chat_id = auth.get('chat_id')
        if chat_id:
            if not isinstance(chat_id, str):
                raise ValueError('Invalid chat')
            chat = await Chats.get_chat_by_id(chat_id)
            if not chat or chat.user_id != user.id:
                raise ValueError('Chat not found')
        model_id = auth.get('model_id')
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError('Select a chat model')
        model_id = model_id.strip()
        if any(ch in model_id for ch in ('\r', '\n', '\x00')):
            raise ValueError('Invalid chat model')
        agent_model = model_id.startswith('agent:')
        if agent_model:
            from open_webui.utils.agents.discovery import get_models as get_agent_models

            machine_id = machine_id_of(auth)
            if not isinstance(machine_id, str) or not machine_id:
                raise ValueError('Select a machine to call an agent')
            parts = model_id.split(':', 3)
            if len(parts) != 4:
                raise ValueError('Invalid agent model')
            # Match HTTP chat authentication for machine connections using session auth.
            ws.state.token = HTTPAuthorizationCredentials(scheme='Bearer', credentials=token)
            candidates = await get_agent_models(
                ws, user, {'machine_id': machine_id, 'chat_id': chat_id}, provider=parts[2]
            )
            model = next((item for item in candidates if item['id'] == model_id), None)
            if model is None:
                raise ValueError('Agent model is unavailable on the selected machine')
        else:
            if not ws.app.state.MODELS:
                await get_all_models(ws, user=user)
            model = ws.app.state.MODELS.get(model_id)
            if not model:
                raise ValueError('Bridge requires a server-configured chat model')
        model_info = await Models.get_model_by_id(model_id)
        if (
            not agent_model
            and not BYPASS_MODEL_ACCESS_CONTROL
            and (user.role != 'admin' or not BYPASS_ADMIN_ACCESS_CONTROL)
        ):
            try:
                await check_model_access(user, model, model_info=model_info)
            except Exception:
                raise ValueError('Chat model access denied') from None

        selected_chat_model = model_id
        if not agent_model:
            base_model_id = getattr(model_info, 'base_model_id', None) if model_info else None
            if not base_model_id and isinstance(model, dict):
                base_model_id = model.get('base_model_id')
            if isinstance(base_model_id, str) and base_model_id.strip():
                selected_chat_model = base_model_id.strip()
        if any(ch in selected_chat_model for ch in ('\r', '\n', '\x00')):
            raise ValueError('Invalid chat model')

        caps = auth.get('capabilities')
        ask_user_enabled = bool(auth.get('ask_user') or (isinstance(caps, list) and 'ask_user' in caps))
        raw_stt_lang = str(auth.get('stt_language') or '').strip().lower()
        stt_language = (
            raw_stt_lang
            if raw_stt_lang
            and raw_stt_lang not in {'auto', 'detect', 'automatic'}
            and _STT_LANG_RE.fullmatch(raw_stt_lang)
            else None
        )

        protocol = CallProtocol(
            model_info.meta.voice_avatar.gestures if model_info and model_info.meta.voice_avatar else (),
            enable_ask_user=ask_user_enabled,
            transcription_model=config.get('audio.realtime.transcription_model'),
        )
        model_meta_dict = model_info.meta.model_dump() if model_info and getattr(model_info, 'meta', None) else {}
        override = ModelVoice.model_validate(model_meta_dict.get('voice') or {})
        voice_model = config.get('audio.realtime.model')
        voice = override.voice or config.get('audio.realtime.voice')
        if not voice_model or not voice or not config.get('audio.realtime.transcription_model'):
            raise ValueError('Configure the Realtime model, voice, and transcription model')
        async with asyncio.timeout(30):
            async with asyncio.timeout(15):
                ws_url, headers = await _get_realtime_connection(config)
                if ENABLE_FORWARD_USER_INFO_HEADERS:
                    headers = include_user_info_headers(headers, user)
                headers['X-Request-ID'] = (
                    ws.headers.get('x-request-id')
                    or ws.headers.get('x-correlation-id')
                    or f'owui-rt-{uuid.uuid4().hex[:16]}'
                )
                stt_profile = ws.headers.get('x-stt-profile')
                if stt_profile:
                    headers['X-STT-Profile'] = stt_profile
                if selected_chat_model and not agent_model:
                    headers['X-Chat-Model'] = selected_chat_model
                session = await get_session()
                try:
                    upstream = await session.ws_connect(
                        ws_url,
                        headers=headers,
                        ssl=AIOHTTP_CLIENT_SESSION_SSL,
                        heartbeat=20,
                        max_msg_size=MAX_EVENT_BYTES,
                    )
                except aiohttp.WSServerHandshakeError as exc:
                    if exc.status in {401, 403}:
                        raise ValueError(
                            'Realtime provider authentication rejected. Check the credentials and access.'
                        ) from None
                    if exc.status == 404:
                        raise ValueError(
                            'Realtime endpoint not found. Check the API base URL and deployment name.'
                        ) from None
                    raise
            event = await upstream.receive_json()
            if event.get('type') != 'session.created':
                raise ValueError('Provider did not create a voice session')
            custom_prompt = (config.get('audio.realtime.prompt_template') or '').strip()
            default_delegation_prompt = (DEFAULT_REALTIME_CALL_PROMPT_TEMPLATE or '').strip()
            has_custom_prompt = bool(
                custom_prompt
                and custom_prompt != default_delegation_prompt
                and 'generate_chat_completion' not in custom_prompt
            )
            model_params = model_meta_dict.get('params') if isinstance(model_meta_dict, dict) else None
            model_system_prompt = (
                (model_params.get('system') or '').strip() if isinstance(model_params, dict) else ''
            )
            if has_custom_prompt:
                session_instructions = custom_prompt
            elif model_system_prompt:
                session_instructions = f'{model_system_prompt}\n\n{DIRECT_REALTIME_CALL_PROMPT}'
            elif protocol.animation_tools or protocol.enable_ask_user:
                session_instructions = DIRECT_REALTIME_CALL_PROMPT
            else:
                session_instructions = None
            if session_instructions and protocol.animation_tools:
                session_instructions = f'{session_instructions}\n{AVATAR_CALL_INSTRUCTIONS}'

            transcription_cfg = {'model': config['audio.realtime.transcription_model']}
            if stt_language:
                transcription_cfg['language'] = stt_language

            session_tools = list(protocol.animation_tools)
            if protocol.enable_ask_user:
                session_tools.append(ASK_USER_REALTIME_TOOL)

            session_update_payload = {
                'type': 'realtime',
                'output_modalities': ['audio'],
                'audio': {
                    'input': {
                        'format': {'type': 'audio/pcm', 'rate': 24000},
                        'transcription': transcription_cfg,
                        # Wait for the finalized transcript before auto/manual turn actions.
                        'turn_detection': {
                            'type': 'server_vad',
                            # The client pauses playback until speech is confirmed.
                            'interrupt_response': False,
                            'create_response': False,
                        },
                        **(config.get('audio.realtime.input_params') or {}),
                    },
                    'output': {'format': {'type': 'audio/pcm', 'rate': 24000}, 'voice': voice},
                },
                'tools': session_tools,
                'tool_choice': 'auto' if session_tools else 'none',
            }
            if session_instructions:
                session_update_payload['instructions'] = session_instructions

            await upstream.send_json(
                {
                    'type': 'session.update',
                    'session': session_update_payload,
                }
            )
            event = await upstream.receive_json()
            if event.get('type') != 'session.updated':
                raise ValueError('Provider rejected voice configuration. Check model, voice, and transcription model.')
        await ws.send_json(
            {
                'type': 'bridge.ready',
                'model': voice_model,
                'chat_model': selected_chat_model,
                'voice': voice,
                'sample_rate': 24000,
            }
        )

        async def client_events():
            while True:
                raw = await ws.receive_text()
                if len(raw.encode()) > MAX_EVENT_BYTES:
                    raise ValueError('Call event is too large')
                event = JSONCodec.loads(raw)
                if event == {'type': 'bridge.ping'}:
                    await ws.send_json({'type': 'bridge.pong'})
                    continue
                try:
                    command = protocol.command(event)
                except (ValueError, TypeError):
                    if not isinstance(event, dict) or event.get('type') != 'conversation.item.truncate':
                        raise
                    await ws.send_json(
                        {'type': 'bridge.error', 'message': 'Invalid audio truncation request', 'fatal': False}
                    )
                    continue
                if event['type'] == 'bridge.result':
                    protocol.requested.add(f'result:{event["call_id"]}')
                for item in command if isinstance(command, list) else [command]:
                    async with asyncio.timeout(5):
                        await upstream.send_json(item)

        async def provider_events():
            async for message in upstream:
                if message.type != aiohttp.WSMsgType.TEXT:
                    raise ValueError('Voice provider connection closed')
                event = message.json()
                if not isinstance(event, dict):
                    raise ValueError('Invalid provider event')
                kind = event.get('type', '')
                if kind == 'error' and event.get('error', {}).get('code') == 'response_cancel_not_active':
                    continue  # Server VAD may finish cancellation before our explicit cancel arrives.
                if kind == 'error':
                    # Provider error text can include prompts or credentials.
                    raise ValueError('Voice provider rejected a request')
                command = protocol.observe(event)
                if command:
                    # Clean up before the client can request another response.
                    async with asyncio.timeout(5):
                        await upstream.send_json(command)
                if kind.startswith(('response.', 'conversation.item.', 'input_audio_buffer.', 'ask_user.')):
                    async with asyncio.timeout(5):
                        await ws.send_json(event)
            raise ValueError('Voice provider connection closed')

        async def check_auth():
            # Also limits a call to the provider's one-hour session lifetime.
            for _ in range(60):
                await asyncio.sleep(60)
                current = await get_verified_user_by_token(token, redis)
                if not current or not await Config.get('audio.realtime.enabled'):
                    raise ValueError('Call authorization expired')
                if current.role != 'admin' and not await has_permission(
                    current.id, 'chat.call', await Config.get('user.permissions') or {}
                ):
                    raise ValueError('Call permission revoked')
            raise ValueError('Call session expired. Start a new call.')

        tasks = [asyncio.create_task(fn()) for fn in (client_events, provider_events, check_auth)]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Only our own validation errors are safe to show. Never stringify provider exceptions.
        detail = (
            str(exc)
            if type(exc) is ValueError
            # A send can still fail on the provider connection that just closed.
            else 'Voice provider connection closed'
            if isinstance(exc, aiohttp.ClientConnectionResetError)
            else ('Voice connection timed out' if isinstance(exc, TimeoutError) else 'Voice connection failed')
        )
        log.info('Bridge closed: user_id=%s error_type=%s', user.id if user else None, type(exc).__name__)
        with contextlib.suppress(Exception):
            await ws.send_json({'type': 'bridge.error', 'message': detail})
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if upstream is not None:
            await upstream.close()
        with contextlib.suppress(Exception):
            await ws.close()
