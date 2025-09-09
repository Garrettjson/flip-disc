import { describe, test, expect, mock } from "bun:test";
import { UIWebSocketHandler } from "./uiSocket";

const createMockWebSocket = () => ({
  send: mock(() => {}),
  close: mock(() => {})
});

const createMockOrchestrator = () => ({
  isRunning: mock(() => false),
  getDisplayInfo: mock(() => ({ canvas_width: 28, canvas_height: 7 })),
  startAnimation: mock(async () => {}),
  server_communication: { isConnected: mock(() => true) },
  frame_scheduler: { getStats: mock(() => ({ credits: 5 })) }
});

describe("Sockets", () => {
  test("handles client connection", () => {
    const handler = new UIWebSocketHandler();
    const mockWs = createMockWebSocket();
    const orchestrator = createMockOrchestrator();
    
    handler.handleOpen(mockWs as any, orchestrator as any);
    
    expect(handler.getClientCount()).toBe(1);
    expect(mockWs.send).toHaveBeenCalled();
  });
  
  test("broadcasts to multiple clients", () => {
    const handler = new UIWebSocketHandler();
    const mockWs1 = createMockWebSocket();
    const mockWs2 = createMockWebSocket();
    const orchestrator = createMockOrchestrator();
    
    handler.handleOpen(mockWs1 as any, orchestrator as any);
    handler.handleOpen(mockWs2 as any, orchestrator as any);
    
    handler.broadcastToAll({ type: 'test' });
    
    expect(mockWs1.send).toHaveBeenCalled();
    expect(mockWs2.send).toHaveBeenCalled();
  });
});