"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { MicIcon, SendIcon, StopIcon } from "@/components/common/Icons";
import { ChatApiError, transcribeAudio } from "@/services/chat-api";

interface Props {
  value: string;
  loading: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
}

export function MessageComposer({ value, loading, onChange, onSubmit, onStop }: Props) {
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserFrameRef = useRef<number | null>(null);
  const voicedFramesRef = useRef(0);
  const recordingStartedAtRef = useRef(0);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [voiceError, setVoiceError] = useState<string | null>(null);

  useEffect(() => {
    if (!recording) return;
    const interval = window.setInterval(() => {
      setRecordingSeconds((seconds) => {
        if (seconds >= 59) {
          recorderRef.current?.stop();
          return 60;
        }
        return seconds + 1;
      });
    }, 1000);
    return () => window.clearInterval(interval);
  }, [recording]);

  useEffect(() => () => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    if (analyserFrameRef.current) window.cancelAnimationFrame(analyserFrameRef.current);
    void audioContextRef.current?.close();
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit();
  }

  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  }

  function stopRecording() {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }

  async function startRecording() {
    setVoiceError(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setVoiceError("Trình duyệt này không hỗ trợ ghi âm.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const audioContext = new AudioContext();
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 512;
      audioContext.createMediaStreamSource(stream).connect(analyser);
      audioContextRef.current = audioContext;
      voicedFramesRef.current = 0;
      const samples = new Uint8Array(analyser.fftSize);
      const detectVoice = () => {
        analyser.getByteTimeDomainData(samples);
        let energy = 0;
        for (const sample of samples) {
          const normalized = (sample - 128) / 128;
          energy += normalized * normalized;
        }
        const rms = Math.sqrt(energy / samples.length);
        if (rms > 0.025) voicedFramesRef.current += 1;
        analyserFrameRef.current = window.requestAnimationFrame(detectVoice);
      };
      detectVoice();
      const preferredType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/mp4")
          ? "audio/mp4"
          : "";
      const recorder = new MediaRecorder(stream, preferredType ? { mimeType: preferredType } : undefined);
      chunksRef.current = [];
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        setRecording(false);
        if (analyserFrameRef.current) window.cancelAnimationFrame(analyserFrameRef.current);
        analyserFrameRef.current = null;
        await audioContext.close();
        audioContextRef.current = null;
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        if (!blob.size) {
          setVoiceError("Bản ghi âm đang trống.");
          return;
        }
        const durationMs = Date.now() - recordingStartedAtRef.current;
        if (durationMs < 700 || voicedFramesRef.current < 6) {
          setVoiceError("Không phát hiện giọng nói. Hãy giữ micro gần hơn và nói lại.");
          return;
        }
        setTranscribing(true);
        try {
          const transcript = await transcribeAudio(blob);
          onChange(value.trim() ? `${value.trim()} ${transcript}` : transcript);
        } catch (cause) {
          setVoiceError(cause instanceof ChatApiError
            ? cause.problem.detail
            : "Không thể nhận dạng giọng nói. Vui lòng thử lại.");
        } finally {
          setTranscribing(false);
        }
      };
      recorder.start(250);
      recordingStartedAtRef.current = Date.now();
      setRecordingSeconds(0);
      setRecording(true);
    } catch (cause) {
      const denied = cause instanceof DOMException && cause.name === "NotAllowedError";
      setVoiceError(denied
        ? "Bạn cần cho phép trình duyệt sử dụng microphone."
        : "Không thể mở microphone. Vui lòng thử lại.");
    }
  }

  return (
    <footer className="composer-wrap">
      {loading && <button className="stop-generation" onClick={onStop}><StopIcon /> Dừng tạo nội dung</button>}
      {(recording || transcribing || voiceError) && (
        <div className={`voice-status ${voiceError ? "error" : ""}`}>
          {recording && <><i /><span>Đang ghi âm · {Math.floor(recordingSeconds / 60)}:{String(recordingSeconds % 60).padStart(2, "0")}</span><button onClick={stopRecording}>Dừng và chuyển thành văn bản</button></>}
          {transcribing && <><span className="voice-spinner" /><span>Đang nhận dạng tiếng Việt...</span></>}
          {voiceError && <><span>{voiceError}</span><button onClick={() => setVoiceError(null)}>Đóng</button></>}
        </div>
      )}
      <form className="composer" onSubmit={submit}>
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={keyDown}
          placeholder="Nhắn tin cho Kori..."
          rows={1}
          maxLength={2000}
          aria-label="Tin nhắn"
        />
        <div className="composer-submit">
          {!value.trim() && (
            <button
              type="button"
              className={`mic-button ${recording ? "recording" : ""}`}
              title={recording ? "Dừng ghi âm" : "Ghi âm"}
              aria-label={recording ? "Dừng ghi âm" : "Ghi âm"}
              disabled={transcribing}
              onClick={recording ? stopRecording : () => void startRecording()}
            >
              {recording ? <StopIcon /> : <MicIcon />}
            </button>
          )}
          {value.trim() && <button type="submit" className="send-button" aria-label="Gửi tin nhắn"><SendIcon /></button>}
        </div>
      </form>
      <p>Kori có thể mắc lỗi. Vui lòng kiểm tra lại thông tin quan trọng.</p>
    </footer>
  );
}
