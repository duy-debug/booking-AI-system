# Booking AI Chatbot Frontend

Next.js customer chat interface for the Booking AI Chatbot.

```powershell
npm install
npm run dev
```

Open `http://localhost:3002`. The Next.js route handler proxies requests to
`CHATBOT_API_URL` (default `http://localhost:8001`), so the browser never calls
the Booking Backend directly.

Set `CHATBOT_API_URL` explicitly in production. The localhost value is intended
only for local development. Voice input is currently hidden because the chatbot
backend does not expose an audio transcription endpoint.
