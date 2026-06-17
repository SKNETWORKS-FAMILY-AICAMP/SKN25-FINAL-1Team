import { useCallback, useRef, useState } from "react";

// 브라우저 SpeechRecognition (벤더 프리픽스 호환) — 타입 미정의라 최소 형태로 선언
type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  onresult: ((event: any) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
};

const getSpeechRecognition = (): SpeechRecognitionLike | null => {
  const Ctor =
    (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
  return Ctor ? (new Ctor() as SpeechRecognitionLike) : null;
};

// STT 녹음 훅 — Groq용 오디오(MediaRecorder) + 실시간 미리보기(Web Speech)를 함께 돌림
export const useVoiceRecording = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [liveText, setLiveText] = useState(""); // 말하는 즉시 흐르는 실시간 전사(미리보기)

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const finalTranscriptRef = useRef(""); // Web Speech 확정 구간 누적
  const keepRecognizingRef = useRef(false); // 무음으로 끊겨도 녹음 중이면 재시작

  // 실시간 미리보기 — Web Speech 시작 (미지원 브라우저면 조용히 건너뜀)
  const startRecognition = useCallback(() => {
    const recognition = getSpeechRecognition();
    if (!recognition) {
      return;
    }
    recognition.lang = "ko-KR";
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onresult = (event: any) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscriptRef.current += transcript;
        } else {
          interim += transcript;
        }
      }
      setLiveText(finalTranscriptRef.current + interim);
    };

    // 무음으로 자동 종료되면 녹음 중인 동안은 다시 켬
    recognition.onend = () => {
      if (keepRecognizingRef.current) {
        try {
          recognition.start();
        } catch {
          // 이미 시작된 경우 등 — 무시
        }
      }
    };
    recognition.onerror = () => {};

    recognitionRef.current = recognition;
    keepRecognizingRef.current = true;
    recognition.start();
  }, []);

  // 녹음 시작 — 마이크 권한 요청 후 오디오 수집 + 실시간 미리보기 동시 시작
  const start = useCallback(async () => {
    setLiveText("");
    finalTranscriptRef.current = "";

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    chunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        chunksRef.current.push(event.data);
      }
    };
    recorder.start();
    recorderRef.current = recorder;

    startRecognition();
    setIsRecording(true);
  }, [startRecognition]);

  // 녹음 정지 — 미리보기 종료 + 오디오 Blob 반환(Groq 최종 전사용)
  const stop = useCallback(() => {
    keepRecognizingRef.current = false;
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // 무시
      }
      recognitionRef.current = null;
    }

    return new Promise<Blob | null>((resolve) => {
      const recorder = recorderRef.current;
      if (!recorder) {
        setIsRecording(false);
        resolve(null);
        return;
      }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        recorder.stream.getTracks().forEach((track) => track.stop());
        recorderRef.current = null;
        setIsRecording(false);
        resolve(blob.size > 0 ? blob : null);
      };
      recorder.stop();
    });
  }, []);

  return { isRecording, liveText, start, stop };
};
