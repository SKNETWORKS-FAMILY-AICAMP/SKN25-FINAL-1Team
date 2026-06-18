import { useCallback, useState } from "react";
import { uploadEmrFile } from "../api/emrApi";
import type { UploadedFile } from "../types/emr";
import { logger } from "../utils/logger";

export function useEmrFile(accessToken: string, isTodayView: boolean) {
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [isUploadingFile, setIsUploadingFile] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const clear = useCallback(() => {
    setUploadedFiles([]);
    setUploadError(null);
  }, []);

  const handleRemoveFile = useCallback((fileId: number) => {
    setUploadedFiles((files) => files.filter((f) => f.id !== fileId));
  }, []);

  const handleUploadFile = useCallback(
    async (file: File) => {
      if (!isTodayView) return;

      setUploadError(null);
      setIsUploadingFile(true);
      try {
        const { cloudfront_url } = await uploadEmrFile({ accessToken, file });
        setUploadedFiles((files) => [
          ...files,
          { id: Date.now(), label: file.name, url: cloudfront_url },
        ]);
      } catch (err: unknown) {
        logger.error("[UploadEmrFile] failed:", err);
        const status = (err as { response?: { status?: number } })?.response?.status;
        setUploadError(
          status === 413
            ? "파일 크기는 50MB 이하만 업로드 가능합니다."
            : "사진 업로드에 실패했습니다. 다시 시도해주세요."
        );
      } finally {
        setIsUploadingFile(false);
      }
    },
    [accessToken, isTodayView]
  );

  return {
    uploadedFiles,
    setUploadedFiles,
    isUploadingFile,
    uploadError,
    setUploadError,
    clear,
    handleRemoveFile,
    handleUploadFile,
  };
}
