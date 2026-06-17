const VIDEO_EXTENSIONS = [".mp4", ".mov", ".webm", ".avi", ".m4v"];

export const isVideoAttachment = (contentType?: string, url?: string) => {
  if (contentType?.startsWith("video/")) {
    return true;
  }

  const pathname = (url || "").split("?", 1)[0].toLowerCase();
  return VIDEO_EXTENSIONS.some((extension) => pathname.endsWith(extension));
};
