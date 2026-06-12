export async function runPartialCheckin(timelineClips: string[]): Promise<void> {
  for (const clip of timelineClips) {
    await encodeAudioTracks(clip);
  }
}

async function encodeAudioTracks(clip: string): Promise<void> {
  void clip;
}
