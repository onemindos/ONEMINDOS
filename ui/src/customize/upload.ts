// SPDX-License-Identifier: Apache-2.0
// "Upload your own" wallpaper: check the file, shrink it in the browser, and sample its colours
// so the contrast guard can pick a safe dim. Nothing leaves the browser except through the
// PreferencesStore the app chose.
import { luminance, rgbToHex } from './color';

export const UPLOAD_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const;
export const UPLOAD_MAX_BYTES = 10 * 1024 * 1024;
export const UPLOAD_MAX_EDGE = 2560;

/** A plain-language reason the file cannot be used, or null when it can. */
export function checkUpload(file: Pick<File, 'type' | 'size'>): string | null {
  if (!(UPLOAD_TYPES as readonly string[]).includes(file.type)) return 'Use a JPEG, PNG or WebP image.';
  if (file.size > UPLOAD_MAX_BYTES) return 'That image is larger than 10 MB. Pick a smaller one.';
  if (file.size === 0) return 'That file is empty.';
  return null;
}

/**
 * Representative colours of RGBA pixels: the darkest and lightest 5 % (by luminance), the
 * median, and two quartiles. Enough for minDim() to bound text contrast.
 */
export function sampleColors(rgba: ArrayLike<number>): string[] {
  const px: string[] = [];
  for (let i = 0; i + 3 < rgba.length; i += 4) {
    if ((rgba[i + 3] ?? 0) < 16) continue;
    px.push(rgbToHex({ r: rgba[i]!, g: rgba[i + 1]!, b: rgba[i + 2]! }));
  }
  if (!px.length) return [];
  const sorted = px.map((c) => [luminance(c), c] as const).sort((a, b) => a[0] - b[0]);
  const at = (q: number) => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))]![1];
  return [...new Set([at(0.05), at(0.25), at(0.5), at(0.75), at(0.95)])];
}

export interface PreparedWallpaper {
  dataUrl: string;
  colors: string[];
  width: number;
  height: number;
}

/** Decode, downscale to UPLOAD_MAX_EDGE, re-encode as JPEG and sample colours. Browser only. */
export async function prepareWallpaper(file: File): Promise<PreparedWallpaper> {
  const reason = checkUpload(file);
  if (reason) throw new Error(reason);
  if (typeof createImageBitmap !== 'function') throw new Error('This browser cannot read images here.');
  let bmp: ImageBitmap;
  try {
    bmp = await createImageBitmap(file);
  } catch {
    throw new Error('That image could not be read. It may be damaged.');
  }
  const scale = Math.min(1, UPLOAD_MAX_EDGE / Math.max(bmp.width, bmp.height));
  const width = Math.max(1, Math.round(bmp.width * scale));
  const height = Math.max(1, Math.round(bmp.height * scale));
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('This browser cannot read images here.');
  ctx.drawImage(bmp, 0, 0, width, height);
  const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
  const small = document.createElement('canvas');
  small.width = 32;
  small.height = 20;
  const sctx = small.getContext('2d');
  let colors: string[] = [];
  if (sctx) {
    sctx.drawImage(bmp, 0, 0, 32, 20);
    colors = sampleColors(sctx.getImageData(0, 0, 32, 20).data);
  }
  bmp.close();
  return { dataUrl, colors, width, height };
}
