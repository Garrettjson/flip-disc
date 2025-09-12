/**
 * Frame Scheduler Service - Manages timing and credit system
 * 
 * Core responsibility: Ensures smooth animation by managing when to generate
 * and send frames based on server credits and target frame rate.
 */

import type { 
  Frame, 
  CreditUpdate, 
  StatusUpdate, 
  DisplayInfo,
  ServerMessage 
} from "@/types/index.ts";

export interface FrameSchedulerConfig {
  target_fps: number;
  max_credits: number;
  credit_threshold: number; // Minimum credits before generating frames
  generate_on_credits?: boolean; // If true, drain credits immediately (burst mode)
}

export type FrameGenerator = () => Promise<Frame | null>;

type SchedulerEvents = {
  frame_ready: Frame;
  credits_updated: { credits: number; buffer_level: number; delta: number };
  frame_error: { error: string };
  status_updated: { server_fps: number; buffer_level: number; frames_displayed: number };
  stopped: ReturnType<FrameSchedulerService['getStats']>;
};

export class FrameSchedulerService {
  private config: FrameSchedulerConfig;
  private credits: number = 0;
  private frame_counter: number = 0;
  private next_frame_time: number = 0;
  private frame_interval: number;
  private running: boolean = false;
  private animation_loop_id: number | null = null;
  private frame_generator: FrameGenerator | null = null;
  private draining: boolean = false;

  // Statistics
  private stats = {
    frames_generated: 0,
    frames_sent: 0,
    frames_dropped: 0,
    credit_updates_received: 0,
    last_fps_calculation: 0,
    fps_samples: [] as number[]
  };

  // Event handlers (multicast by event type)
  private handlers: Map<keyof SchedulerEvents, Set<(data: any) => void>> = new Map();

  constructor(config: FrameSchedulerConfig) {
    this.config = config;
    this.frame_interval = 1000 / config.target_fps; // milliseconds per frame
  }

  /**
   * Start the frame scheduling loop
   */
  start(frameGenerator: FrameGenerator): void {
    if (this.running) {
      console.log("Frame scheduler already running");
      return;
    }

    this.frame_generator = frameGenerator;
    this.running = true;
    this.next_frame_time = performance.now();
    
    console.log(`Starting frame scheduler at ${this.config.target_fps} FPS`);
    
    // If configured to generate on credits, start draining now; otherwise start paced loop
    if (this.config.generate_on_credits) {
      void this.drainCredits();
    } else {
      this.scheduleNextFrame();
    }
  }

  /**
   * Stop the frame scheduling loop
   */
  stop(): void {
    if (!this.running) {
      return;
    }

    this.running = false;
    
    if (this.animation_loop_id !== null) {
      clearTimeout(this.animation_loop_id);
      this.animation_loop_id = null;
    }

    console.log("Frame scheduler stopped");
    this.emit('stopped', this.getStats());
  }

  /**
   * Update credits from server
   */
  updateCredits(creditUpdate: CreditUpdate): void {
    const old_credits = this.credits;
    this.credits = creditUpdate.credits;
    this.stats.credit_updates_received++;

    console.log(`Credits updated: ${old_credits} → ${this.credits} (buffer: ${(creditUpdate.buffer_level * 100).toFixed(1)}%)`);
    
    this.emit('credits_updated', {
      credits: this.credits,
      buffer_level: creditUpdate.buffer_level,
      delta: this.credits - old_credits
    });

    // If we now have credits and were waiting, drain or generate next
    if (this.credits > this.config.credit_threshold) {
      if (this.config.generate_on_credits) {
        void this.drainCredits();
      } else if (this.animation_loop_id === null && this.running) {
        this.scheduleNextFrame();
      }
    }
  }

  /**
   * Handle server status updates
   */
  handleStatusUpdate(status: StatusUpdate): void {
    // Update FPS tracking
    if (this.stats.last_fps_calculation > 0) {
      const time_diff = status.timestamp - this.stats.last_fps_calculation;
      if (time_diff > 0) {
        const actual_fps = 1000 / time_diff; // Convert to FPS
        this.stats.fps_samples.push(actual_fps);
        
        // Keep only last 10 samples for rolling average
        if (this.stats.fps_samples.length > 10) {
          this.stats.fps_samples.shift();
        }
      }
    }
    
    this.stats.last_fps_calculation = status.timestamp;
    
      this.emit('status_updated', {
        server_fps: status.fps_actual,
        buffer_level: status.buffer_level,
        frames_displayed: status.frames_displayed
      });
  }

  /**
   * Schedule the next frame generation
   */
  private scheduleNextFrame(): void {
    if (!this.running) return;

    const now = performance.now();
    const time_until_next = Math.max(0, this.next_frame_time - now);
    
    this.animation_loop_id = setTimeout(() => {
      // Only attempt generation if we have credits; otherwise pause the loop
      if (this.credits > this.config.credit_threshold) {
        this.tryGenerateFrame();

        // Schedule next frame
        this.next_frame_time += this.frame_interval;
        if (this.next_frame_time < performance.now()) {
          this.next_frame_time = performance.now() + this.frame_interval;
        }
        this.scheduleNextFrame();
      } else {
        // Pause until credits arrive
        this.animation_loop_id = null;
        this.next_frame_time = performance.now() + this.frame_interval;
      }
    }, time_until_next);
  }

  /**
   * Try to generate and send a frame if conditions are met
   */
  private async tryGenerateFrame(): Promise<void> {
    if (!this.running || !this.frame_generator) {
      return;
    }

    // Check if we have enough credits
    if (this.credits <= this.config.credit_threshold) {
      // Don't spam logs; the loop will pause and resume on credits
      return;
    }

    try {
      // Generate frame
      const frame = await this.frame_generator();
      
      if (!frame) {
        // Generator returned null (e.g., animation ended)
        return;
      }

      // Assign frame ID
      frame.frame_id = ++this.frame_counter;
      frame.timestamp = performance.now();

      this.stats.frames_generated++;

      // Consume a credit (optimistically - server will update us)
      this.credits = Math.max(0, this.credits - 1);

      // Emit frame ready event
      this.emit('frame_ready', frame);

      console.log(`Generated frame ${frame.frame_id} (credits: ${this.credits + 1} → ${this.credits})`);

    } catch (error) {
      console.error("Error generating frame:", error);
      this.emit('frame_error', { error: (error as any)?.message ?? String(error) });
    }
  }

  /**
   * Drain available credits by generating frames sequentially.
   * Yields to the event loop between frames to avoid blocking.
   */
  private async drainCredits(): Promise<void> {
    if (!this.running || this.draining || !this.frame_generator) return;
    this.draining = true;
    try {
      while (this.running && this.credits > this.config.credit_threshold) {
        await this.tryGenerateFrame();
        // Yield to allow WS/event processing
        await new Promise((r) => setTimeout(r, 0));
      }
    } finally {
      this.draining = false;
    }
  }

  /**
   * Update configuration
   */
  updateConfig(newConfig: Partial<FrameSchedulerConfig>): void {
    const oldFps = this.config.target_fps;
    
    this.config = { ...this.config, ...newConfig };
    
    // Update frame interval if FPS changed
    if (this.config.target_fps !== oldFps) {
      this.frame_interval = 1000 / this.config.target_fps;
      console.log(`Frame scheduler FPS updated: ${oldFps} → ${this.config.target_fps}`);
    }
  }

  /**
   * Get current statistics
   */
  getStats() {
    const avg_fps = this.stats.fps_samples.length > 0
      ? this.stats.fps_samples.reduce((a, b) => a + b, 0) / this.stats.fps_samples.length
      : 0;

    return {
      credits: this.credits,
      frame_counter: this.frame_counter,
      running: this.running,
      target_fps: this.config.target_fps,
      average_fps: avg_fps,
      ...this.stats
    };
  }

  /**
   * Get current scheduler state
   */
  getState() {
    return {
      credits: this.credits,
      frame_counter: this.frame_counter,
      running: this.running,
      next_frame_time: this.next_frame_time,
      target_fps: this.config.target_fps
    };
  }

  /**
   * Register event handler
   */
  on<K extends keyof SchedulerEvents>(event: K, handler: (data: SchedulerEvents[K]) => void): void {
    const set = this.handlers.get(event) ?? new Set();
    set.add(handler as any);
    this.handlers.set(event, set);
  }

  off<K extends keyof SchedulerEvents>(event: K, handler?: (data: SchedulerEvents[K]) => void): void {
    if (!handler) {
      this.handlers.delete(event);
      return;
    }
    this.handlers.get(event)?.delete(handler as any);
  }

  private emit<K extends keyof SchedulerEvents>(event: K, data: SchedulerEvents[K]): void {
    const set = this.handlers.get(event);
    if (!set) return;
    for (const h of set) {
      try { (h as any)(data); } catch (e) { console.error('Scheduler handler error:', e); }
    }
  }

  /**
   * Initialize scheduler with display info
   */
  initialize(displayInfo: DisplayInfo): void {
    // Set max credits based on server buffer size
    const estimated_buffer_size = Math.ceil(displayInfo.refresh_rate * 0.5); // 0.5s buffer
    this.config.max_credits = estimated_buffer_size;
    
    console.log(`Frame scheduler initialized for ${displayInfo.canvas_width}×${displayInfo.canvas_height} display`);
    console.log(`Target FPS: ${this.config.target_fps}, Max credits: ${this.config.max_credits}`);
  }

  /**
   * Reset scheduler state
   */
  reset(): void {
    this.stop();
    this.credits = 0;
    this.frame_counter = 0;
    this.next_frame_time = 0;
    this.stats = {
      frames_generated: 0,
      frames_sent: 0,
      frames_dropped: 0,
      credit_updates_received: 0,
      last_fps_calculation: 0,
      fps_samples: []
    };
  }
}

// Default configuration
export const defaultFrameSchedulerConfig: FrameSchedulerConfig = {
  target_fps: 15, // Conservative default
  max_credits: 15, // Will be updated based on server info
  credit_threshold: 1, // Generate frames when we have at least 1 credit
  generate_on_credits: true
};

// Factory function
export function createFrameScheduler(config?: Partial<FrameSchedulerConfig>): FrameSchedulerService {
  const fullConfig = { ...defaultFrameSchedulerConfig, ...config };
  return new FrameSchedulerService(fullConfig);
}
