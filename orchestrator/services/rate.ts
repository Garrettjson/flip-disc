import { state } from "../state";

export function updateRateForFps(fps: number) {
  const rateState = state.rate;
  const fpsRounded = Math.max(1, Math.round(fps));
  rateState.capacity = fpsRounded;
  rateState.refillPerSec = fpsRounded;
  rateState.tokens = Math.min(rateState.tokens, rateState.capacity);
}

export function canSendNow(now = Date.now()): boolean {
  const rateState = state.rate;
  const dtSec = Math.max(0, (now - rateState.lastRefillMs) / 1000);
  const underPenalty = now < rateState.penaltyUntil;
  const refill = dtSec * (underPenalty ? rateState.refillPerSec / Math.max(1, rateState.penaltyMultiplier) : rateState.refillPerSec);
  rateState.tokens = Math.min(rateState.capacity, rateState.tokens + refill);
  rateState.lastRefillMs = now;
  if (rateState.tokens >= 1) {
    rateState.tokens -= 1;
    return true;
  }
  return false;
}

export function penalize(waitMs: number) {
  const now = Date.now();
  const until = now + Math.max(0, waitMs);
  state.rate.penaltyUntil = Math.max(state.rate.penaltyUntil, until);
}
