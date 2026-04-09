"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { apiGet, apiPut } from "@/lib/api";
import { CheckCircle2, Eye, EyeOff, Key, Save } from "lucide-react";

interface Config {
  has_api_key: boolean;
  soniox_api_key_masked: string;
  default_language: string;
  enable_speaker_diarization: boolean;
  translation_mode: string;
}

export default function SettingsPage() {
  const [config, setConfig] = useState<Config | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [keyLoaded, setKeyLoaded] = useState(false);
  const [defaultLang, setDefaultLang] = useState("en");
  const [diarization, setDiarization] = useState(false);
  const [translationMode, setTranslationMode] = useState("none");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet<Config>("/api/config").then((data) => {
      setConfig(data);
      setDefaultLang(data.default_language);
      setDiarization(data.enable_speaker_diarization);
      setTranslationMode(data.translation_mode);
    });
  }, []);

  const loadFullKey = async () => {
    if (keyLoaded) {
      setShowKey(!showKey);
      return;
    }
    const data = await apiGet<{ soniox_api_key: string }>("/api/config/key");
    setApiKey(data.soniox_api_key);
    setKeyLoaded(true);
    setShowKey(true);
  };

  const handleSave = async () => {
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      const update: Record<string, unknown> = {
        default_language: defaultLang,
        enable_speaker_diarization: diarization,
        translation_mode: translationMode,
      };
      if (keyLoaded && apiKey !== undefined) {
        update.soniox_api_key = apiKey;
      }
      await apiPut("/api/config", update);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  if (!config) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8">
        <p className="text-muted-foreground">Loading settings...</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Configure your Soniox API key and default transcription preferences.
        </p>
      </div>

      <div className="space-y-6">
        {/* API Key */}
        <Card className="p-6">
          <div className="mb-4 flex items-center gap-2">
            <Key className="text-primary h-4 w-4" />
            <h2 className="font-medium">Soniox API Key</h2>
          </div>
          <p className="text-muted-foreground mb-4 text-sm">
            Get your API key from{" "}
            <a
              href="https://console.soniox.com"
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline underline-offset-4"
            >
              console.soniox.com
            </a>
          </p>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Input
                type={showKey ? "text" : "password"}
                placeholder={
                  config.has_api_key ? config.soniox_api_key_masked : "Enter your Soniox API key"
                }
                value={keyLoaded ? apiKey : ""}
                onChange={(e) => {
                  setApiKey(e.target.value);
                  if (!keyLoaded) setKeyLoaded(true);
                }}
              />
            </div>
            <Button variant="outline" size="icon" onClick={loadFullKey} type="button">
              {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </Button>
          </div>
          {config.has_api_key && !keyLoaded && (
            <p className="text-muted-foreground mt-2 text-xs">
              API key is saved. Click the eye icon to reveal or type a new one to replace it.
            </p>
          )}
        </Card>

        {/* Defaults */}
        <Card className="p-6">
          <h2 className="mb-4 font-medium">Default Preferences</h2>
          <div className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="default-lang">Default Language</Label>
              <Select value={defaultLang} onValueChange={(v) => v && setDefaultLang(v)}>
                <SelectTrigger id="default-lang" className="w-full max-w-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="en">English only</SelectItem>
                  <SelectItem value="hi">Hindi only</SelectItem>
                  <SelectItem value="en,hi">English + Hindi</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Separator />

            <div className="flex items-center justify-between">
              <div>
                <Label htmlFor="default-diarize">Speaker Diarization</Label>
                <p className="text-muted-foreground text-sm">
                  Label different speakers in the transcript
                </p>
              </div>
              <Switch id="default-diarize" checked={diarization} onCheckedChange={setDiarization} />
            </div>

            <Separator />

            <div className="space-y-2">
              <Label htmlFor="translation">Translation Mode</Label>
              <Select value={translationMode} onValueChange={(v) => v && setTranslationMode(v)}>
                <SelectTrigger id="translation" className="w-full max-w-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Transcribe as spoken (no translation)</SelectItem>
                  <SelectItem value="to_english">Translate everything to English</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-muted-foreground text-xs">
                This can be overridden per transcription on the home page.
              </p>
            </div>
          </div>
        </Card>

        {/* Save */}
        <div className="flex items-center gap-4">
          <Button onClick={handleSave} disabled={saving}>
            {saving ? (
              <Save className="mr-2 h-4 w-4 animate-pulse" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            Save Settings
          </Button>
          {saved && (
            <span className="flex items-center gap-1.5 text-sm text-green-600 dark:text-green-400">
              <CheckCircle2 className="h-4 w-4" />
              Saved
            </span>
          )}
          {error && <span className="text-destructive text-sm">{error}</span>}
        </div>
      </div>
    </div>
  );
}
