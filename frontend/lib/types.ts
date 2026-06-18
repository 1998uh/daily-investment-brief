export interface User {
  id: string;
  username: string;
  email?: string;
}

export interface Session {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface Attachment {
  id: string;
  filename: string;
  mime: string;
  size: number;
  kind: 'text' | 'image';
  extracted_text?: string;
  data_uri?: string;
}

export interface Message {
  id: number;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  agent?: string;
  sources?: Source[];
  thinking_steps?: ThinkingStep[];
  attachments?: Attachment[];
  created_at: string;
}

export interface Source {
  title: string;
  author: string;
  date: string;
  url?: string;
  source?: string;
  kind?: 'local' | 'web';
}

export interface ThinkingStep {
  agent: string;
  text: string;
}

export interface SSEEvent {
  type: 'thinking' | 'token' | 'done' | 'session_id' | 'error';
  agent?: string;
  text?: string;
  sources?: Source[];
  session_id?: string;
  message?: string;
}

export interface WatchItem {
  symbol: string;
  note?: string;
  added_at: string;
}

export interface Trade {
  id: number;
  symbol: string;
  action: string;
  price?: number;
  quantity?: number;
  trade_date?: string;
  note?: string;
  created_at: string;
}

export interface Event {
  id: number;
  title: string;
  content?: string;
  event_date?: string;
  tags?: string[];
  created_at: string;
}

export interface ChatState {
  sessionId: string | null;
  messages: Message[];
  isStreaming: boolean;
  thinkingSteps: ThinkingStep[];
  currentTokens: string;
  error: string | null;
}
