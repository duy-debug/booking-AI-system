"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChatApiError, streamChat } from "@/services/chat-api";
import {
  getOrCreateConversationId,
  resetConversationId,
  saveConversationSession,
} from "@/services/chat-session";
import type { ChatMessage } from "@/types/chat";

const WELCOME_TEXT = "Xin chào! Mình là Kori, trợ lý wellness của Komorebi. Mình có thể giúp anh/chị đặt lịch và giải đáp thông tin dịch vụ. Hôm nay anh/chị cần mình hỗ trợ gì?";

function welcomeMessage(): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: "assistant",
    text: WELCOME_TEXT,
    createdAt: Date.now(),
  };
}

export function useBookingChat() {
  const [conversationId, setConversationId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [streamingStarted, setStreamingStarted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryText, setRetryText] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const inFlightRef = useRef(false);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const id = getOrCreateConversationId(sessionStorage);
      setConversationId(id);
      setMessages([welcomeMessage()]);
    });
    return () => {
      window.cancelAnimationFrame(frame);
      abortRef.current?.abort();
    };
  }, []);

  const sendMessage = useCallback(async (rawText: string) => {
    const text = rawText.trim();
    if (!text || text.length > 2000 || !conversationId || inFlightRef.current) return;
    inFlightRef.current = true;
    const controller = new AbortController();
    abortRef.current = controller;
    setIsSending(true);
    setStreamingStarted(false);
    setError(null);
    setRetryText(null);
    saveConversationSession(sessionStorage, conversationId);
    let streamingAssistantId: string | null = null;
    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: "user",
        text,
        createdAt: Date.now(),
        status: "sending",
      },
    ]);

    try {
      await streamChat(
        { conversation_id: conversationId, message: text, signal: controller.signal },
        {
          onStarted: () => {
            setStreamingStarted(true);
            setMessages((current) => current.map((message) => (
              message.role === "user" && message.status === "sending"
                ? { ...message, status: "sent" as const }
                : message
            )));
          },
          onDelta: (event) => {
            if (!event.text) return;
            setStreamingStarted(false);
            setMessages((current) => {
              if (streamingAssistantId === null) {
                streamingAssistantId = crypto.randomUUID();
                return [
                  ...current,
                  {
                    id: streamingAssistantId,
                    role: "assistant",
                    text: event.text,
                    createdAt: Date.now(),
                  },
                ];
              }
              return current.map((message) => (
                message.id === streamingAssistantId
                  ? { ...message, text: message.text + event.text }
                  : message
              ));
            });
          },
          onMessage: (result) => {
            setStreamingStarted(false);
            setMessages((current) => {
              const messagesWithSentUser = current.map((message) => (
                message.role === "user" && message.status === "sending"
                  ? { ...message, status: "sent" as const }
                  : message
              ));
              if (streamingAssistantId !== null) {
                return messagesWithSentUser.map((message) => (
                  message.id === streamingAssistantId
                    ? { ...message, text: result.text, response: result }
                    : message
                ));
              }
              return [
                ...messagesWithSentUser,
                {
                  id: crypto.randomUUID(),
                  role: "assistant",
                  text: result.text,
                  response: result,
                  createdAt: Date.now(),
                },
              ];
            });
          },
        },
      );
    } catch (cause) {
      const problem = cause instanceof ChatApiError ? cause.problem : null;
      if (problem?.code === "cancelled") {
        setMessages((current) => current.map((message) => (
          message.role === "user" && message.status === "sending"
            ? { ...message, status: "sent" as const }
            : message
        )));
      } else {
        setMessages((current) => current
          .map((message) => (
            message.role === "user" && message.status === "sending"
              ? { ...message, status: "failed" as const }
              : message
          )));
        setError(problem?.detail ?? "Không thể kết nối đến trợ lý.");
        if (problem?.code !== "stream_interrupted" && problem?.code !== "timeout") {
          setRetryText(text);
        }
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      inFlightRef.current = false;
      setIsSending(false);
      setStreamingStarted(false);
    }
  }, [conversationId]);

  const retryLastMessage = useCallback(() => {
    if (!retryText || inFlightRef.current) return;
    void sendMessage(retryText);
  }, [retryText, sendMessage]);

  const cancelCurrentRequest = useCallback(() => abortRef.current?.abort(), []);

  const resetConversation = useCallback(() => {
    abortRef.current?.abort();
    inFlightRef.current = false;
    const id = resetConversationId(sessionStorage);
    setConversationId(id);
    setMessages([welcomeMessage()]);
    setIsSending(false);
    setStreamingStarted(false);
    setError(null);
    setRetryText(null);
  }, []);

  return {
    messages,
    conversationId,
    isSending,
    streamingStarted,
    error,
    canRetry: retryText !== null,
    sendMessage,
    retryLastMessage,
    resetConversation,
    cancelCurrentRequest,
  };
}
