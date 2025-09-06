// Orchestrator preload: runs before entrypoints via bunfig.toml
// Useful for global setup, logging tweaks, env validation, etc.

// Example: normalize SIGINT in case entrypoint forgets to register
try {
  const onSig = () => { /* no-op; main registers real shutdown */ };
  // @ts-ignore Node-style process may not exist in all Bun targets
  process?.on?.('SIGINT', onSig);
  process?.on?.('SIGTERM', onSig);
} catch {}

// Keep minimal to avoid side effects; main index.ts sets up real handlers

