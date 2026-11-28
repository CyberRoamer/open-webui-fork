FROM ghcr.io/open-webui/open-webui:v0.13.5

# Bundle SHA-256-verified v0.13.5 mobile realtime, Standard Voice ask_user, Live Mode Speech Coach, and voice pipeline patches and Speech Coach tools
COPY patches/v0.13.5/B1EqPYAs.js /opt/realtime-patch/B1EqPYAs.js
COPY patches/v0.13.5/CaoI0pp2.js /opt/realtime-patch/CaoI0pp2.js
COPY patches/v0.13.5/asset_versioner.py /opt/realtime-patch/asset_versioner.py
COPY patches/v0.13.5/ask_user.py /opt/realtime-patch/ask_user.py
COPY patches/v0.13.5/builtin.py /opt/realtime-patch/builtin.py
COPY patches/v0.13.5/middleware.py /opt/realtime-patch/middleware.py
COPY patches/v0.13.5/headers.py /opt/realtime-patch/headers.py
COPY patches/v0.13.5/audio_init.py /opt/realtime-patch/audio_init.py
COPY patches/v0.13.5/audio_realtime.py /opt/realtime-patch/audio_realtime.py
COPY patches/v0.13.5/coolify_entrypoint.sh /opt/realtime-patch/entrypoint.sh
COPY tools/ /opt/openwebui-tools/

RUN chmod 0755 /opt/realtime-patch/entrypoint.sh && \
    chmod 0644 /opt/realtime-patch/B1EqPYAs.js /opt/realtime-patch/CaoI0pp2.js /opt/realtime-patch/asset_versioner.py /opt/realtime-patch/ask_user.py /opt/realtime-patch/builtin.py /opt/realtime-patch/middleware.py /opt/realtime-patch/headers.py /opt/realtime-patch/audio_init.py /opt/realtime-patch/audio_realtime.py && \
    printf '%s\n' \
      '29d6b2a2e76eff38c3bd7602c006459ed8d19c405eeaa06b28da52b81347e31c  /app/build/_app/immutable/chunks/B1EqPYAs.js' \
      '7611058e08d300631a1d481bea550389eba07a5ac873611e814139f86f5bdd94  /app/build/_app/immutable/chunks/CaoI0pp2.js' \
      '8538e5effbda42c310573e6a5be718b8ea655ddb90c5360b25bf1386a74e5c5d  /app/backend/open_webui/utils/ask_user.py' \
      '1bd4ce2bd8a8aaf180a5a0783a616519968de62eaea1c87b54536c51e560d59c  /app/backend/open_webui/tools/builtin.py' \
      '919b4dc69c6356d65ed1198467710f00933de3b08825f5c5b96a5f3d5f066f7d  /app/backend/open_webui/utils/middleware.py' \
      '2601a71db5eadd258d5dc89b40023d4c470063357bdeafe939cbcda45a32a432  /app/backend/open_webui/utils/headers.py' \
      'f22233f795444da1773f07043e478b77f915bde5633580a9f231b4eed864dd40  /app/backend/open_webui/routers/audio/__init__.py' \
      '0226a1501401e08804c3501474de847e454d12f98ae938eb83cfc678e1b4a830  /app/backend/open_webui/routers/audio/realtime.py' \
      | sha256sum -c - && \
    cp -p /app/build/_app/immutable/chunks/B1EqPYAs.js /app/build/_app/immutable/chunks/B1EqPYAs.js.orig && \
    cp -p /app/build/_app/immutable/chunks/CaoI0pp2.js /app/build/_app/immutable/chunks/CaoI0pp2.js.orig && \
    cp -p /app/backend/open_webui/utils/ask_user.py /app/backend/open_webui/utils/ask_user.py.orig && \
    cp -p /app/backend/open_webui/tools/builtin.py /app/backend/open_webui/tools/builtin.py.orig && \
    cp -p /app/backend/open_webui/utils/middleware.py /app/backend/open_webui/utils/middleware.py.orig && \
    cp -p /app/backend/open_webui/utils/headers.py /app/backend/open_webui/utils/headers.py.orig && \
    cp -p /app/backend/open_webui/routers/audio/__init__.py /app/backend/open_webui/routers/audio/__init__.py.orig && \
    cp -p /app/backend/open_webui/routers/audio/realtime.py /app/backend/open_webui/routers/audio/realtime.py.orig && \
    install -m 0644 /opt/realtime-patch/B1EqPYAs.js /app/build/_app/immutable/chunks/B1EqPYAs.js && \
    install -m 0644 /opt/realtime-patch/CaoI0pp2.js /app/build/_app/immutable/chunks/CaoI0pp2.js && \
    install -m 0644 /opt/realtime-patch/ask_user.py /app/backend/open_webui/utils/ask_user.py && \
    install -m 0644 /opt/realtime-patch/builtin.py /app/backend/open_webui/tools/builtin.py && \
    install -m 0644 /opt/realtime-patch/middleware.py /app/backend/open_webui/utils/middleware.py && \
    install -m 0644 /opt/realtime-patch/headers.py /app/backend/open_webui/utils/headers.py && \
    install -m 0644 /opt/realtime-patch/audio_init.py /app/backend/open_webui/routers/audio/__init__.py && \
    install -m 0644 /opt/realtime-patch/audio_realtime.py /app/backend/open_webui/routers/audio/realtime.py && \
    for pair in \
      "/opt/realtime-patch/B1EqPYAs.js:/app/build/_app/immutable/chunks/B1EqPYAs.js" \
      "/opt/realtime-patch/CaoI0pp2.js:/app/build/_app/immutable/chunks/CaoI0pp2.js" \
      "/opt/realtime-patch/ask_user.py:/app/backend/open_webui/utils/ask_user.py" \
      "/opt/realtime-patch/builtin.py:/app/backend/open_webui/tools/builtin.py" \
      "/opt/realtime-patch/middleware.py:/app/backend/open_webui/utils/middleware.py" \
      "/opt/realtime-patch/headers.py:/app/backend/open_webui/utils/headers.py" \
      "/opt/realtime-patch/audio_init.py:/app/backend/open_webui/routers/audio/__init__.py" \
      "/opt/realtime-patch/audio_realtime.py:/app/backend/open_webui/routers/audio/realtime.py"; do \
      src="${pair%%:*}"; dst="${pair#*:}"; \
      printf '%s  %s\n' "$(sha256sum "$src" | awk '{print $1}')" "$dst"; \
    done | sha256sum -c - && \
    python3 /opt/realtime-patch/asset_versioner.py --build-dir /app/build --seeds B1EqPYAs.js CaoI0pp2.js

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=20s \
  CMD curl -s -f http://localhost:8080/health || exit 1

ENTRYPOINT ["/bin/bash", "/opt/realtime-patch/entrypoint.sh"]
