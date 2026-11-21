import { ChatRequest, ChatResponse } from './types';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? 'http://localhost:8000';

export async function sendMessage(req: ChatRequest): Promise<ChatResponse> {
  const response = await fetch(`${BACKEND_URL}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(req),
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const err = await response.json();
      if (err.detail) detail = err.detail;
    } catch {
      // ignore JSON parse error
    }
    throw new Error(detail);
  }

  return response.json() as Promise<ChatResponse>;
}
