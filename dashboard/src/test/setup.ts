import '@testing-library/jest-dom';

// Mock WebSocket globally
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState = MockWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;

  constructor(_url: string) {
    setTimeout(() => this.onopen?.(), 0);
  }

  send(_data: string) {}
  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }
}

Object.defineProperty(global, 'WebSocket', { value: MockWebSocket, writable: true });

// Mock fetch globally — individual tests override per-case
global.fetch = vi.fn();
