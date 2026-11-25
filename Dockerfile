FROM ghcr.io/open-webui/open-webui:v0.13.5

# Bundle SHA-256-verified v0.13.5 mobile realtime + ask_user patches and Speech Coach tools
COPY patches/v0.13.5/B1EqPYAs.js /opt/realtime-patch/B1EqPYAs.js
COPY patches/v0.13.5/ask_user.py /opt/realtime-patch/ask_user.py
COPY patches/v0.13.5/builtin.py /opt/realtime-patch/builtin.py
COPY patches/v0.13.5/coolify_entrypoint.sh /opt/realtime-patch/entrypoint.sh
COPY tools/ /opt/openwebui-tools/

RUN chmod 0755 /opt/realtime-patch/entrypoint.sh && \
    chmod 0644 /opt/realtime-patch/B1EqPYAs.js /opt/realtime-patch/ask_user.py /opt/realtime-patch/builtin.py && \
    printf '%s\n' \
      '29d6b2a2e76eff38c3bd7602c006459ed8d19c405eeaa06b28da52b81347e31c  /app/build/_app/immutable/chunks/B1EqPYAs.js' \
      '8538e5effbda42c310573e6a5be718b8ea655ddb90c5360b25bf1386a74e5c5d  /app/backend/open_webui/utils/ask_user.py' \
      '1bd4ce2bd8a8aaf180a5a0783a616519968de62eaea1c87b54536c51e560d59c  /app/backend/open_webui/tools/builtin.py' \
      | sha256sum -c - && \
    cp -p /app/build/_app/immutable/chunks/B1EqPYAs.js /app/build/_app/immutable/chunks/B1EqPYAs.js.orig && \
    cp -p /app/backend/open_webui/utils/ask_user.py /app/backend/open_webui/utils/ask_user.py.orig && \
    cp -p /app/backend/open_webui/tools/builtin.py /app/backend/open_webui/tools/builtin.py.orig && \
    install -m 0644 /opt/realtime-patch/B1EqPYAs.js /app/build/_app/immutable/chunks/B1EqPYAs.js && \
    install -m 0644 /opt/realtime-patch/ask_user.py /app/backend/open_webui/utils/ask_user.py && \
    install -m 0644 /opt/realtime-patch/builtin.py /app/backend/open_webui/tools/builtin.py && \
    printf '%s\n' \
      'b2644911f0aeb9c7786f004f6b725cef71bfc8363aa083be98e58371cdd3d86c  /app/build/_app/immutable/chunks/B1EqPYAs.js' \
      '984e19f255f7cadc6839147acee4502d58fd80f4c75ef7c90c61cb4fae89b16b  /app/backend/open_webui/utils/ask_user.py' \
      '7e0134597c37b08deb79845d84435c94b6fef3c0c342b58237934ddef18045b0  /app/backend/open_webui/tools/builtin.py' \
      | sha256sum -c -

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=20s \
  CMD curl -s -f http://localhost:8080/health || exit 1

ENTRYPOINT ["/bin/bash", "/opt/realtime-patch/entrypoint.sh"]
