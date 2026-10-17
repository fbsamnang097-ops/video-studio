# Deploy to Render

1. Push this folder to a GitHub repo (private is fine).
2. Render dashboard > New > Blueprint > pick the repo. It reads `render.yaml`.
   (Or: New > Web Service > Docker, Dockerfile path `./Dockerfile`, health check `/health`.)
3. Set `APP_PASSWORD` when asked. Anyone with the URL could otherwise use your server.
4. Open the `.onrender.com` URL and sign in.

Optional environment variables
- `YT_COOKIES`   contents of a Netscape cookies.txt (helps when YouTube blocks the server)
- `YTDLP_PROXY`  e.g. http://user:pass@host:port
- `CLEANUP_HOURS` hours to keep downloads (default 2)

AI features (Whisper + speakers): edit the Dockerfile line `ARG WITH_AI=0` to `ARG WITH_AI=1`
and use a plan with at least 2 GB RAM. Use the Google engine for translation on the server.
