# AgriSense frontend

The AgriSense farmer workspace is a React, TypeScript, and Vite application. It uses the checked-in `../docs/openapi.json` contract for API types and reads the API origin from `VITE_API_URL`.

## Run locally

Use Node.js 20.19 or newer. From the repository root:

### macOS

```sh
cd frontend
cp .env.example .env
npm install
npm run generate:api
npm run dev
```

### Windows PowerShell

```powershell
Set-Location frontend
Copy-Item .env.example .env
npm install
npm run generate:api
npm run dev
```

By default, the frontend expects the FastAPI service at `http://localhost:8000`. Set `VITE_API_URL` in `frontend/.env` when the API uses another origin. The backend must have a valid `JWT_SECRET` and an allowed CORS origin for `http://localhost:5173`.

## Demo preview

Set `VITE_ENABLE_API_MOCKS=true` in `frontend/.env` to use the isolated, typed preview service in `src/api/mock.ts`. Demo data is labelled in the interface and stays in the browser; this mode does not call the backend. Set the flag to `false` for normal API use.

## Checks

```sh
npm run lint
npm run build
```

`npm run generate:api` regenerates `src/api/openapi.ts` from the repository OpenAPI document. Update the API document first when backend paths or schemas change.
