export class BadRequest extends Error {
  status = 400;
  constructor(message: string) { super(message); }
}

export const badRequest = (message: string) => new Response(message, { status: 400 });

export const parseJson = async <T = unknown>(req: Request, fallback: T | null = null): Promise<T> => {
  try {
    return await req.json() as T;
  } catch {
    if (fallback !== null) return fallback as T;
    throw new BadRequest('invalid json');
  }
};

export const ensureNumber = (value: unknown, field: string, opts?: { min?: number; max?: number; integer?: boolean }) => {
  const numberValue = Number((value as any));
  if (!Number.isFinite(numberValue)) throw new BadRequest(`${field} must be a number`);
  if (opts?.integer && !Number.isInteger(numberValue)) throw new BadRequest(`${field} must be an integer`);
  if (opts?.min !== undefined && numberValue < opts.min) throw new BadRequest(`${field} must be >= ${opts.min}`);
  if (opts?.max !== undefined && numberValue > opts.max) throw new BadRequest(`${field} must be <= ${opts.max}`);
  return numberValue;
};

export const ensureString = (value: unknown, field: string) => {
  if (typeof value !== 'string' || value.length === 0) throw new BadRequest(`${field} must be a non-empty string`);
  return value;
};

export const isRecord = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
