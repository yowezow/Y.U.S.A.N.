export type CoreResponse = {
  type: "system_action" | "llm_response" | "configuration_required" | "error";
  content?: string;
  action?: string;
  success?: boolean;
  message?: string;
};

export type LLMConfigStatus = {
  configured: boolean;
  provider: string;
  model: string;
  status: "configured" | "api_key_required" | "connected" | "invalid_api_key" | "model_unavailable" | "permission_denied" | "quota_exceeded" | "connection_failed" | "service_error" | "unknown_error" | "invalid_provider";
};

export type LLMConnectionStatus = {
  success: boolean;
  authenticated: boolean | null;
  provider: string;
  model?: string | null;
  status: LLMConfigStatus["status"];
  error_type?: string | null;
  message?: string | null;
};

export type LLMModelsStatus = {
  models: string[];
  selected_model?: string | null;
  provider: string;
  status: LLMConfigStatus["status"];
  error_type?: string | null;
  message?: string | null;
};

export type CoreRuntimeStatus = {
  state: "starting" | "online" | "offline" | "error";
  endpoint: string;
  message: string;
};

export type ConfigRequestErrorDetail = {
  stage: string;
  code: string;
  message: string;
};

export class ConfigRequestError extends Error {
  constructor(public readonly detail: ConfigRequestErrorDetail, public readonly status: number) {
    super(detail.message);
    this.name = "ConfigRequestError";
  }
}

export class CoreUnavailableError extends Error {
  constructor(public readonly status: CoreRuntimeStatus) {
    super(status.message);
    this.name = "CoreUnavailableError";
  }
}

const CORE_REQUEST_TIMEOUT_MS = 8_000;

function safeCredentialLog(stage: string, details: Record<string, string | number | boolean>) {
  console.info(`[YUSAN credential] ${stage}`, details);
}

function isConfigErrorDetail(value: unknown): value is ConfigRequestErrorDetail {
  return typeof value === "object" && value !== null
    && typeof (value as ConfigRequestErrorDetail).stage === "string"
    && typeof (value as ConfigRequestErrorDetail).code === "string"
    && typeof (value as ConfigRequestErrorDetail).message === "string";
}

export function isConfigRequestError(error: unknown): error is ConfigRequestError {
  return error instanceof ConfigRequestError;
}

export function isCoreUnavailableError(error: unknown): error is CoreUnavailableError {
  return error instanceof CoreUnavailableError;
}

export function getCoreStatus(): Promise<CoreRuntimeStatus> {
  return invoke<CoreRuntimeStatus>("core_status");
}

async function coreUrl(): Promise<string> {
  const status = await getCoreStatus();
  if (status.state !== "online" || !status.endpoint) throw new CoreUnavailableError(status);
  return status.endpoint;
}

async function coreFetch(path: string, options?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), CORE_REQUEST_TIMEOUT_MS);
  try {
    return await fetch(`${await coreUrl()}${path}`, { ...options, signal: controller.signal });
  } catch (error) {
    if (error instanceof CoreUnavailableError) throw error;
    throw new Error("YUSAN Core'a bağlanılamadı.");
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function sendToCore(message: string): Promise<CoreResponse> {
  const response = await coreFetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message })
  });
  if (!response.ok) throw new Error("YUSAN Core'a bağlanılamadı.");
  return response.json() as Promise<CoreResponse>;
}

async function configRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await coreFetch(path, options);
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = typeof body === "object" && body !== null ? (body as { detail?: unknown }).detail : null;
    if (isConfigErrorDetail(detail)) {
      safeCredentialLog("backend response error", { status: response.status, stage: detail.stage, code: detail.code });
      throw new ConfigRequestError(detail, response.status);
    }
    throw new Error("YUSAN Core'a bağlanılamadı.");
  }
  return response.json() as Promise<T>;
}

export function getLLMConfig(): Promise<LLMConfigStatus> {
  return configRequest<LLMConfigStatus>("/api/config/llm");
}

export function getLLMModels(): Promise<LLMModelsStatus> {
  return configRequest<LLMModelsStatus>("/api/config/llm/models");
}

export function saveLLMKey(provider: string, apiKey: string): Promise<LLMConfigStatus> {
  safeCredentialLog("webview request prepared", {
    provider,
    apiKeyReceived: typeof apiKey === "string" && apiKey.length > 0,
    apiKeyLength: apiKey.length
  });
  return configRequest<LLMConfigStatus>("/api/config/llm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, api_key: apiKey })
  });
}

export function testLLMConnection(provider: string): Promise<LLMConnectionStatus> {
  return configRequest<LLMConnectionStatus>("/api/config/llm/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider })
  });
}

export function selectLLMModel(provider: string, model: string): Promise<LLMConfigStatus> {
  return configRequest<LLMConfigStatus>("/api/config/llm/model", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, model })
  });
}
import { invoke } from "@tauri-apps/api/core";
