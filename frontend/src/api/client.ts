import createClient from "openapi-fetch";
import type { components, paths } from "./openapi";
import { mockApi } from "./mock";

export type User = components["schemas"]["UserPublic"];
export type TokenResponse = components["schemas"]["TokenResponse"];
export type Field = components["schemas"]["FieldRead"];
export type FieldCreate = components["schemas"]["FieldCreate"];
export type FieldUpdate = components["schemas"]["FieldUpdate"];
export type Reading = components["schemas"]["ReadingRead"];
export type ReadingCreate = components["schemas"]["ReadingCreate"];
export type CSVImportResponse = components["schemas"]["CSVImportResponse"];
export type Weather = components["schemas"]["WeatherRead"];
export type Decision = components["schemas"]["IrrigationDecisionRead"];
export type DecisionRequest = components["schemas"]["IrrigationDecisionRequest"];
export type OverrideRequest = components["schemas"]["OverrideRequest"];
export type KnowledgeBase = components["schemas"]["KBRead"];
export type AboutSystem = components["schemas"]["AboutSystemRead"];
export type Health = components["schemas"]["HealthRead"];

const API_BASE_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const MOCKS_ENABLED = import.meta.env.VITE_ENABLE_API_MOCKS === "true";
const TOKEN_KEY = "agrisense.accessToken";
const REQUEST_TIMEOUT_MS = 12_000;
export const AUTH_EXPIRED_EVENT = "agrisense:auth-expired";
export const API_READY_EVENT = "agrisense:api-ready";

export function getAccessToken(): string | null {
  return window.sessionStorage.getItem(TOKEN_KEY);
}

export function saveAccessToken(token: string): void {
  window.sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  window.sessionStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

function messageFromPayload(payload: unknown, fallback: string): string {
  if (typeof payload === "string") return payload;
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = payload.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((item) => {
        if (item && typeof item === "object" && "msg" in item && typeof item.msg === "string") return item.msg;
        return "Check the submitted information.";
      }).join(" ");
    }
  }
  return fallback;
}

async function timeoutFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(new DOMException("Request timed out", "TimeoutError")), REQUEST_TIMEOUT_MS);
  const sourceSignal = init?.signal;
  const abortFromSource = () => controller.abort(sourceSignal?.reason);
  sourceSignal?.addEventListener("abort", abortFromSource, { once: true });
  if (sourceSignal?.aborted) abortFromSource();
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted && !sourceSignal?.aborted) {
      throw new ApiError("The request took too long. The service may be waking; please try again.");
    }
    if (error instanceof TypeError) {
      throw new ApiError("AgriSense could not reach the API. Check the connection and try again.");
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
    sourceSignal?.removeEventListener("abort", abortFromSource);
  }
}

const client = createClient<paths>({ baseUrl: API_BASE_URL, fetch: timeoutFetch });
client.use({
  onRequest({ request }) {
    const token = getAccessToken();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401) window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
    return response;
  },
});

type OpenApiResult<T> = { data?: T; error?: unknown; response: Response };

async function unwrap<T>(operation: Promise<OpenApiResult<T>>): Promise<T> {
  let result: OpenApiResult<T>;
  try {
    result = await operation;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(error instanceof Error ? error.message : "The API request failed.");
  }
  if (!result.response.ok || result.error !== undefined) {
    const errorPayload = result.error;
    throw new ApiError(messageFromPayload(errorPayload, `The API returned ${result.response.status}.`), result.response.status);
  }
  if (result.response.status === 204) return undefined as T;
  if (result.data === undefined) throw new ApiError("The API returned an empty response.", result.response.status);
  return result.data;
}

async function uploadCsv(fieldId: number, file: File): Promise<CSVImportResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const headers = new Headers();
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await timeoutFetch(`${API_BASE_URL}/fields/${fieldId}/readings/csv`, {
      method: "POST",
      body: formData,
      headers,
    });
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(error instanceof Error ? error.message : "CSV upload failed.");
  }
  if (response.status === 401) window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
  const payload: unknown = await response.json().catch(() => undefined);
  if (!response.ok) throw new ApiError(messageFromPayload(payload, `CSV upload failed (${response.status}).`), response.status);
  return payload as CSVImportResponse;
}

export interface AgriSenseApi {
  health(): Promise<Health>;
  register(body: components["schemas"]["RegisterRequest"]): Promise<TokenResponse>;
  login(body: components["schemas"]["LoginRequest"]): Promise<TokenResponse>;
  me(): Promise<User>;
  listFields(): Promise<Field[]>;
  getField(fieldId: number): Promise<Field>;
  createField(body: FieldCreate): Promise<Field>;
  updateField(fieldId: number, body: FieldUpdate): Promise<Field>;
  deleteField(fieldId: number): Promise<void>;
  getReadings(fieldId: number, limit?: number): Promise<Reading[]>;
  createReading(fieldId: number, body: ReadingCreate): Promise<Reading>;
  uploadReadingsCsv(fieldId: number, file: File): Promise<CSVImportResponse>;
  getWeather(fieldId: number): Promise<Weather>;
  decideIrrigation(fieldId: number, body: DecisionRequest): Promise<Decision>;
  getIrrigationHistory(fieldId: number, limit?: number): Promise<Decision[]>;
  overrideIrrigation(decisionId: number, body: OverrideRequest): Promise<Decision>;
  getKnowledgeBase(kind: string): Promise<KnowledgeBase>;
  getAboutSystem(): Promise<AboutSystem>;
}

const realApi: AgriSenseApi = {
  health: () => unwrap(client.GET("/health")),
  register: (body) => unwrap(client.POST("/auth/register", { body })),
  login: (body) => unwrap(client.POST("/auth/login", { body })),
  me: () => unwrap(client.GET("/me")),
  listFields: () => unwrap(client.GET("/fields")),
  getField: (fieldId) => unwrap(client.GET("/fields/{field_id}", { params: { path: { field_id: fieldId } } })),
  createField: (body) => unwrap(client.POST("/fields", { body })),
  updateField: (fieldId, body) => unwrap(client.PUT("/fields/{field_id}", { params: { path: { field_id: fieldId } }, body })),
  deleteField: (fieldId) => unwrap(client.DELETE("/fields/{field_id}", { params: { path: { field_id: fieldId } } })),
  getReadings: (fieldId, limit = 100) => unwrap(client.GET("/fields/{field_id}/readings", { params: { path: { field_id: fieldId }, query: { limit } } })),
  createReading: (fieldId, body) => unwrap(client.POST("/fields/{field_id}/readings", { params: { path: { field_id: fieldId } }, body })),
  uploadReadingsCsv: uploadCsv,
  getWeather: (fieldId) => unwrap(client.GET("/fields/{field_id}/weather", { params: { path: { field_id: fieldId } } })),
  decideIrrigation: (fieldId, body) => unwrap(client.POST("/fields/{field_id}/irrigation/decide", { params: { path: { field_id: fieldId } }, body })),
  getIrrigationHistory: (fieldId, limit = 100) => unwrap(client.GET("/fields/{field_id}/irrigation/history", { params: { path: { field_id: fieldId }, query: { limit } } })),
  overrideIrrigation: (decisionId, body) => unwrap(client.POST("/irrigation/{decision_id}/override", { params: { path: { decision_id: decisionId } }, body })),
  getKnowledgeBase: (kind) => unwrap(client.GET("/kb/{kind}", { params: { path: { kind } } })),
  getAboutSystem: () => unwrap(client.GET("/about/system")),
};

export const api: AgriSenseApi = MOCKS_ENABLED ? mockApi : realApi;
