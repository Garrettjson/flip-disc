/**
 * Workers API Route
 * GET /api/workers - List available animation workers
 */

import type { FlipDiscOrchestrator } from "@/index.ts";
import { Glob } from "bun";

export async function getWorkers(request: Request, orchestrator: FlipDiscOrchestrator): Promise<Response> {
  try {
    // Find worker files in the workers directory
    const glob = new Glob("**/*-worker.ts");
    const workerFiles = Array.from(glob.scanSync("./src/workers"));
    
    const workers = workerFiles.map(file => {
      // Extract worker name from filename
      const name = file.replace(/.*\//, '').replace('-worker.ts', '');
      const id = name.replace(/[^a-z0-9]/gi, '-').toLowerCase();
      
      return {
        id,
        name: name.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' '),
        path: `./src/workers/${file.replace(/.*\//, '')}`,
        description: getWorkerDescription(name)
      };
    });
    
    return Response.json({ 
      workers,
      count: workers.length
    });
    
  } catch (error) {
    return Response.json(
      { error: "Failed to list workers" }, 
      { status: 500 }
    );
  }
}

function getWorkerDescription(name: string): string {
  const descriptions: Record<string, string> = {
    'bouncing-dot': 'Simple dot that bounces around the display',
    'spiral': 'Spiral pattern animation',
    'wave': 'Wave motion across the display',
    'text-scroll': 'Scrolling text animation'
  };
  
  return descriptions[name] || `${name} animation worker`;
}