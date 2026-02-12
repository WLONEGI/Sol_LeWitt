export type AspectRatio = '16:9' | '4:3' | '4:5' | '1:1' | '2:3' | '3:4' | '9:16' | '21:9';

export const ASPECT_RATIO_MAP: Record<string, string> = {
    '16:9': 'aspect-[16/9]',
    '4:3': 'aspect-[4/3]',
    '4:5': 'aspect-[4/5]',
    '1:1': 'aspect-square',
    '2:3': 'aspect-[2/3]',
    '3:4': 'aspect-[3/4]',
    '9:16': 'aspect-[9/16]',
    '21:9': 'aspect-[21/9]',
};

export function getAspectRatioClass(ratio?: string): string {
    if (!ratio) return ASPECT_RATIO_MAP['16:9'];
    return ASPECT_RATIO_MAP[ratio] || ASPECT_RATIO_MAP['16:9'];
}
