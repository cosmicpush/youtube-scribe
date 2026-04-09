"use client";

import { useState, useCallback, useEffect } from "react";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { apiPost, apiGet, downloadUrl } from "@/lib/api";
import {
  Loader2,
  FileText,
  Subtitles,
  Play,
  AlertCircle,
  CheckCircle2,
  RotateCcw,
} from "lucide-react";

interface VideoInfo {
  id: string;
  title: string;
  duration: number;
  channel: string;
  thumbnail: string;
}

interface Job {
  id: string;
  status: string;
  progress: string;
  youtube_url: string;
  video_info: VideoInfo | null;
  transcript_text: string | null;
  transcript_srt: string | null;
  error: string | null;
}

const STATUS_PROGRESS: Record<string, number> = {
  downloading: 20,
  uploading: 40,
  transcribing: 70,
  completed: 100,
  error: 0,
};

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function HomePage() {
  const [url, setUrl] = useState("");
  const [languageHints, setLanguageHints] = useState("en,hi");
  const [diarization, setDiarization] = useState(false);
  const [translateToEnglish, setTranslateToEnglish] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const pollJob = useCallback(async (jobId: string) => {
    try {
      const data = await apiGet<Job>(`/api/jobs/${jobId}`);
      setJob(data);
      if (data.status !== "completed" && data.status !== "error") {
        setTimeout(() => pollJob(jobId), 2000);
      }
    } catch {
      setTimeout(() => pollJob(jobId), 3000);
    }
  }, []);

  // Restore active job on page load / refresh
  useEffect(() => {
    apiGet<Job | null>("/api/jobs/active/latest")
      .then((data) => {
        if (data && data.id) {
          setJob(data);
          setUrl(data.youtube_url || "");
          if (data.status !== "completed" && data.status !== "error") {
            pollJob(data.id);
          }
        }
      })
      .catch(() => {});
  }, [pollJob]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setJob(null);
    setSubmitting(true);

    try {
      const hints = languageHints
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const data = await apiPost<{ job_id: string }>("/api/transcribe", {
        youtube_url: url,
        language_hints: hints,
        enable_speaker_diarization: diarization,
        translate_to_english: translateToEnglish,
      });
      setJob({
        id: data.job_id,
        status: "downloading",
        progress: "Starting...",
        youtube_url: url,
        video_info: null,
        transcript_text: null,
        transcript_srt: null,
        error: null,
      });
      pollJob(data.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start transcription");
    } finally {
      setSubmitting(false);
    }
  };

  const handleRetry = async () => {
    if (!job) return;
    try {
      await apiPost(`/api/jobs/${job.id}/retry`, {});
      setJob({ ...job, status: "retrying", progress: "Retrying...", error: null });
      pollJob(job.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to retry");
    }
  };

  const isProcessing = job && job.status !== "completed" && job.status !== "error";

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Transcribe a YouTube Video</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Paste a YouTube link below to get a full transcript powered by Soniox AI.
        </p>
      </div>

      <Card className="p-6">
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="url">YouTube URL</Label>
            <div className="flex gap-2">
              <Input
                id="url"
                type="url"
                placeholder="https://www.youtube.com/watch?v=..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                required
                disabled={!!isProcessing}
                className="flex-1"
              />
              <Button type="submit" disabled={!url || !!isProcessing || submitting}>
                {submitting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                <span className="ml-2">{submitting ? "Starting..." : "Transcribe"}</span>
              </Button>
            </div>
          </div>

          <Separator />

          <div className="grid grid-cols-1 items-center gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="lang">Language Hints</Label>
              <Select value={languageHints} onValueChange={(v) => v && setLanguageHints(v)}>
                <SelectTrigger id="lang">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="en">English only</SelectItem>
                  <SelectItem value="hi">Hindi only</SelectItem>
                  <SelectItem value="en,hi">English + Hindi</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center gap-2">
              <Switch id="diarize" checked={diarization} onCheckedChange={setDiarization} />
              <Label htmlFor="diarize" className="text-sm">
                Speaker labels
              </Label>
            </div>

            <div className="flex items-center gap-2">
              <Switch
                id="translate"
                checked={translateToEnglish}
                onCheckedChange={setTranslateToEnglish}
              />
              <Label htmlFor="translate" className="text-sm">
                Translate to English
              </Label>
            </div>
          </div>
        </form>
      </Card>

      {error && (
        <Alert variant="destructive" className="mt-6">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {job && (
        <Card className="mt-6 p-6">
          {/* Video info */}
          {job.video_info && (
            <div className="mb-4 flex items-start gap-4">
              {job.video_info.thumbnail && (
                <Image
                  src={job.video_info.thumbnail}
                  alt=""
                  width={144}
                  height={80}
                  className="h-20 w-36 rounded-md object-cover"
                  unoptimized
                />
              )}
              <div className="min-w-0 flex-1">
                <h3 className="truncate font-medium">{job.video_info.title}</h3>
                <p className="text-muted-foreground text-sm">{job.video_info.channel}</p>
                <Badge variant="secondary" className="mt-1">
                  {formatDuration(job.video_info.duration)}
                </Badge>
              </div>
            </div>
          )}

          {/* Progress */}
          {isProcessing && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm">
                <Loader2 className="text-primary h-4 w-4 animate-spin" />
                <span>{job.progress}</span>
              </div>
              <Progress value={STATUS_PROGRESS[job.status] || 10} />
            </div>
          )}

          {/* Error */}
          {job.status === "error" && (
            <div className="space-y-3">
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{job.error}</AlertDescription>
              </Alert>
              <Button variant="outline" size="sm" onClick={handleRetry}>
                <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
                Retry (resumes from last step)
              </Button>
            </div>
          )}

          {/* Completed */}
          {job.status === "completed" && job.transcript_text && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
                  <CheckCircle2 className="h-4 w-4" />
                  <span>Transcription complete</span>
                </div>
                <div className="flex gap-2">
                  <a href={downloadUrl(`/api/jobs/${job.id}/download/txt`)} download>
                    <Button variant="outline" size="sm">
                      <FileText className="mr-1.5 h-3.5 w-3.5" />
                      .txt
                    </Button>
                  </a>
                  <a href={downloadUrl(`/api/jobs/${job.id}/download/srt`)} download>
                    <Button variant="outline" size="sm">
                      <Subtitles className="mr-1.5 h-3.5 w-3.5" />
                      .srt
                    </Button>
                  </a>
                </div>
              </div>
              <Separator />
              <ScrollArea className="h-[400px] rounded-md border p-4">
                <pre className="font-mono text-sm leading-relaxed whitespace-pre-wrap">
                  {job.transcript_text}
                </pre>
              </ScrollArea>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
