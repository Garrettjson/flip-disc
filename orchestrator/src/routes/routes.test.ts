import { describe, test, expect, mock } from "bun:test";
import { getStatus } from "./status";
import { startAnimation } from "./animation";

const createMockOrchestrator = () => ({
  isRunning: mock(() => false),
  getDisplayInfo: mock(() => ({ canvas_width: 28, canvas_height: 7 })),
  startAnimation: mock(async () => {}),
  server_communication: { isConnected: mock(() => true) },
  frame_scheduler: { getStats: mock(() => ({ credits: 5 })) }
});

describe("Routes", () => {
  test("status returns orchestrator info", async () => {
    const orchestrator = createMockOrchestrator();
    const response = await getStatus(new Request("http://localhost"), orchestrator as any);
    
    expect(response.status).toBe(200);
    const data = await response.json();
    expect(data.running).toBe(false);
    expect(data.server_connected).toBe(true);
  });

  test("animation start requires worker_path", async () => {
    const orchestrator = createMockOrchestrator();
    const request = new Request("http://localhost", {
      method: "POST",
      body: JSON.stringify({})
    });
    
    const response = await startAnimation(request, orchestrator as any);
    expect(response.status).toBe(400);
  });
});