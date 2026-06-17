import { useState, type ChangeEvent } from "react";

import { uploadChatAttachment } from "../api/chat-api";
import { useTranslation } from "../i18n/language-context";

export interface PendingAttachment {
  fileName: string;
  contentType: string;
  cloudfrontUrl: string;
  previewUrl: string;
}

const allowedAttachmentTypes = ["image/jpeg", "image/png", "video/mp4", "video/quicktime"];

interface UseChatUploadParams {
  setErrorMessage: (message: string) => void;
  getErrorMessage: (error: unknown, fallbackMessage: string) => string;
}

export const useChatUpload = ({
  setErrorMessage,
  getErrorMessage,
}: UseChatUploadParams) => {
  const { t } = useTranslation();
  const [pendingAttachment, setPendingAttachment] =
    useState<PendingAttachment | null>(null);
  const [isUploadingAttachment, setIsUploadingAttachment] = useState(false);

  const clearPendingAttachment = () => {
    if (pendingAttachment?.previewUrl.startsWith("blob:")) {
      URL.revokeObjectURL(pendingAttachment.previewUrl);
    }

    setPendingAttachment(null);
  };

  const handleSelectAttachment = async (
    event: ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) {
      return;
    }

    if (!allowedAttachmentTypes.includes(file.type)) {
      setErrorMessage(t("chatbot.uploadTypeError"));
      return;
    }

    try {
      setIsUploadingAttachment(true);
      setErrorMessage("");

      const response = await uploadChatAttachment(file);
      if (
        response.code !== 200 ||
        !response.result?.cloudfront_url
      ) {
        setErrorMessage(
          response.message || t("chatbot.uploadFailed"),
        );
        return;
      }

      if (pendingAttachment?.previewUrl.startsWith("blob:")) {
        URL.revokeObjectURL(pendingAttachment.previewUrl);
      }

      setPendingAttachment({
        fileName: file.name,
        contentType: file.type,
        cloudfrontUrl: response.result.cloudfront_url,
        previewUrl: URL.createObjectURL(file),
      });
    } catch (error) {
      setErrorMessage(getErrorMessage(error, t("chatbot.uploadFailed")));
    } finally {
      setIsUploadingAttachment(false);
    }
  };

  return {
    pendingAttachment,
    setPendingAttachment,
    clearPendingAttachment,
    handleSelectAttachment,
    isUploadingAttachment,
  };
};
