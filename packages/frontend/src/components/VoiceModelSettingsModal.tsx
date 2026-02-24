import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Mic, X, Eye, EyeOff } from 'lucide-react';
import type { BidiModelType, VoiceModelConfig } from '../hooks/useVoiceChat';
import { useModal } from '../hooks/useModal';

const VOICE_MODEL_STORAGE_KEY = 'voice_model_config';

function obfuscate(value: string): string {
  return btoa(
    Array.from(new TextEncoder().encode(value), (b) =>
      String.fromCharCode(b),
    ).join(''),
  );
}

function deobfuscate(encoded: string): string {
  try {
    const binary = atob(encoded);
    return new TextDecoder().decode(
      Uint8Array.from(binary, (c) => c.charCodeAt(0)),
    );
  } catch {
    return encoded;
  }
}

export interface VoiceModelSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (config: VoiceModelConfig) => void;
  selectedModel?: BidiModelType; // If provided, only show settings for this model
}

const MODEL_OPTIONS: {
  value: BidiModelType;
  label: string;
  requiresApiKey: boolean;
}[] = [
  { value: 'nova_sonic', label: 'Amazon Nova Sonic', requiresApiKey: false },
  { value: 'gemini', label: 'Google Gemini Live', requiresApiKey: true },
  { value: 'openai', label: 'OpenAI Realtime', requiresApiKey: true },
];

const VOICE_OPTIONS: Record<BidiModelType, { value: string; label: string }[]> =
  {
    nova_sonic: [
      { value: 'tiffany', label: 'Tiffany (Female)' },
      { value: 'matthew', label: 'Matthew (Male)' },
    ],
    gemini: [
      { value: 'Kore', label: 'Kore (Female)' },
      { value: 'Puck', label: 'Puck (Male)' },
      { value: 'Charon', label: 'Charon (Male)' },
      { value: 'Fenrir', label: 'Fenrir (Male)' },
      { value: 'Aoede', label: 'Aoede (Female)' },
    ],
    openai: [
      { value: 'alloy', label: 'Alloy' },
      { value: 'ash', label: 'Ash' },
      { value: 'ballad', label: 'Ballad' },
      { value: 'coral', label: 'Coral' },
      { value: 'echo', label: 'Echo' },
      { value: 'sage', label: 'Sage' },
      { value: 'shimmer', label: 'Shimmer' },
      { value: 'verse', label: 'Verse' },
    ],
  };

export function getStoredVoiceModelConfig(): VoiceModelConfig {
  try {
    const stored = localStorage.getItem(VOICE_MODEL_STORAGE_KEY);
    if (stored) {
      const config = JSON.parse(stored) as VoiceModelConfig;
      // Decode obfuscated API keys
      const decoded: Record<string, string> = {};
      if (config.apiKeys) {
        for (const [k, v] of Object.entries(config.apiKeys)) {
          decoded[k] = v ? deobfuscate(v) : '';
        }
      }
      config.apiKeys = decoded as VoiceModelConfig['apiKeys'];
      config.apiKey =
        decoded[config.modelType as 'gemini' | 'openai'] || undefined;
      return config;
    }
  } catch {
    // ignore
  }
  return { modelType: 'nova_sonic', voice: 'tiffany', apiKeys: {} };
}

export function saveVoiceModelConfig(config: VoiceModelConfig): void {
  // Obfuscate API keys before persisting
  const encoded: Record<string, string> = {};
  if (config.apiKeys) {
    for (const [k, v] of Object.entries(config.apiKeys)) {
      encoded[k] = v ? obfuscate(v) : '';
    }
  }
  const toStore = {
    ...config,
    apiKey: undefined,
    apiKeys: encoded,
  };
  localStorage.setItem(VOICE_MODEL_STORAGE_KEY, JSON.stringify(toStore));
}

function getApiKeyForModel(
  config: VoiceModelConfig,
  modelType: BidiModelType,
): string {
  if (modelType === 'nova_sonic') return '';
  return config.apiKeys?.[modelType] || '';
}

export default function VoiceModelSettingsModal({
  isOpen,
  onClose,
  onSave,
  selectedModel,
}: VoiceModelSettingsModalProps) {
  const { t } = useTranslation();
  const [modelType, setModelType] = useState<BidiModelType>('nova_sonic');
  const [apiKey, setApiKey] = useState('');
  const [voice, setVoice] = useState('tiffany');
  const [showApiKey, setShowApiKey] = useState(false);
  const [storedApiKeys, setStoredApiKeys] = useState<{
    gemini?: string;
    openai?: string;
  }>({});
  const [modelUnlocked, setModelUnlocked] = useState(false);
  const tapCountRef = useRef(0);
  const tapTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  // If selectedModel is provided, lock to that model (unless unlocked via hidden tap)
  const isModelLocked = selectedModel !== undefined && !modelUnlocked;
  const effectiveModelType = isModelLocked ? selectedModel : modelType;

  useEffect(() => {
    if (isOpen) {
      setModelUnlocked(false);
      tapCountRef.current = 0;
      const config = getStoredVoiceModelConfig();
      const targetModel = selectedModel ?? config.modelType;
      setModelType(targetModel);
      setStoredApiKeys(config.apiKeys || {});
      setApiKey(getApiKeyForModel(config, targetModel));
      const storedVoice =
        config.modelType === targetModel ? config.voice : undefined;
      setVoice(storedVoice || VOICE_OPTIONS[targetModel][0]?.value || '');
    }
  }, [isOpen, selectedModel]);

  useEffect(() => {
    if (!isOpen) return;
    // Reset voice when model changes - check if current voice is valid for new model
    const voices = VOICE_OPTIONS[effectiveModelType];
    const isVoiceValidForModel = voices?.some((v) => v.value === voice);
    if (!isVoiceValidForModel && voices && voices.length > 0) {
      setVoice(voices[0].value);
    }
    // Load stored API key for this model
    setApiKey(storedApiKeys[effectiveModelType as 'gemini' | 'openai'] || '');
  }, [effectiveModelType, storedApiKeys, isOpen, voice]);

  useModal({ isOpen, onClose });

  const handleSave = () => {
    // Update stored API keys with current key
    const updatedApiKeys = { ...storedApiKeys };
    if (effectiveModelType === 'gemini' || effectiveModelType === 'openai') {
      if (apiKey.trim()) {
        updatedApiKeys[effectiveModelType] = apiKey.trim();
      } else {
        delete updatedApiKeys[effectiveModelType];
      }
    }

    const config: VoiceModelConfig = {
      modelType: effectiveModelType,
      voice,
      apiKey: apiKey.trim() || undefined,
      apiKeys: updatedApiKeys,
    };

    saveVoiceModelConfig(config);
    onSave(config);
    onClose();
  };

  const modelOption = MODEL_OPTIONS.find((m) => m.value === effectiveModelType);
  const requiresApiKey = modelOption?.requiresApiKey ?? false;

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/55 dark:bg-black/65 backdrop-blur-md"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="voice-settings-modal relative rounded-2xl w-full max-w-md mx-4 flex flex-col overflow-hidden border border-white/70 dark:border-indigo-500/20 shadow-[0_25px_60px_-15px_rgba(0,0,0,0.15)] dark:shadow-[0_0_80px_rgba(99,102,241,0.08),0_25px_50px_-12px_rgba(0,0,0,0.5)]">
        {/* Gradient glow */}
        <div
          className="dark:hidden absolute inset-0 pointer-events-none rounded-2xl"
          style={{
            background:
              'radial-gradient(ellipse 60% 50% at 80% 0%, rgba(139, 92, 246, 0.1) 0%, transparent 70%)',
          }}
        />
        <div
          className="hidden dark:block absolute inset-0 pointer-events-none rounded-2xl"
          style={{
            background:
              'radial-gradient(ellipse 60% 50% at 80% 0%, rgba(139, 92, 246, 0.15) 0%, transparent 70%)',
          }}
        />

        {/* Header */}
        <div className="flex items-center gap-3 p-4 border-b border-black/[0.06] dark:border-[#2a2f45] flex-shrink-0">
          <Mic className="h-5 w-5 text-purple-500" />
          <h2 className="text-lg font-semibold text-[#1e293b] dark:text-[#f8fafc]">
            {t('voiceModel.settings', 'Voice Model Settings')}
          </h2>
          <button
            onClick={onClose}
            className="ml-auto p-1.5 hover:bg-white/40 dark:hover:bg-[#1e2235] rounded-lg transition-colors"
          >
            <X className="h-5 w-5 text-[#64748b]" />
          </button>
        </div>

        {/* Content */}
        <div className="relative p-4 space-y-4">
          {/* Model Selection */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-[#334155] dark:text-[#cbd5e1]">
              {t('voiceModel.model', 'Model')}
            </label>
            {isModelLocked ? (
              <div
                className="w-full px-3 py-2 text-sm bg-transparent dark:bg-[#0d1117] border border-black/10 dark:border-[#3b4264] rounded-lg text-[#475569] dark:text-[#cbd5e1] select-none cursor-default"
                onClick={() => {
                  tapCountRef.current += 1;
                  clearTimeout(tapTimerRef.current);
                  if (tapCountRef.current >= 5) {
                    tapCountRef.current = 0;
                    setModelUnlocked(true);
                  } else {
                    tapTimerRef.current = setTimeout(() => {
                      tapCountRef.current = 0;
                    }, 1500);
                  }
                }}
              >
                {modelOption?.label || effectiveModelType}
              </div>
            ) : (
              <select
                data-modal-input
                value={modelType}
                onChange={(e) => setModelType(e.target.value as BidiModelType)}
                className="w-full px-3 py-2 text-sm border border-black/10 dark:border-[#3b4264] rounded-lg bg-transparent dark:bg-[#0d1117] text-[#0f172a] dark:text-[#f1f5f9] focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              >
                {MODEL_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* API Key (conditional) */}
          {requiresApiKey && (
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-[#334155] dark:text-[#cbd5e1]">
                {t('voiceModel.apiKey', 'API Key')}
              </label>
              <div className="relative">
                <input
                  data-modal-input
                  type={showApiKey ? 'text' : 'password'}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={modelType === 'gemini' ? 'AIza...' : 'sk-...'}
                  className="w-full px-3 py-2 pr-10 text-sm border border-black/10 dark:border-[#3b4264] rounded-lg bg-transparent dark:bg-[#0d1117] text-[#0f172a] dark:text-[#f1f5f9] placeholder-[#94a3b8] focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 text-[#94a3b8] hover:text-[#475569] dark:hover:text-[#cbd5e1] transition-colors"
                >
                  {showApiKey ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
              <p className="text-xs text-[#64748b]">
                {t(
                  'voiceModel.apiKeyHint',
                  'Stored locally in your browser only',
                )}
              </p>
            </div>
          )}

          {/* Voice Selection */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-[#334155] dark:text-[#cbd5e1]">
              {t('voiceModel.voice', 'Voice')}
            </label>
            <select
              data-modal-input
              value={voice}
              onChange={(e) => setVoice(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-black/10 dark:border-[#3b4264] rounded-lg bg-transparent dark:bg-[#0d1117] text-[#0f172a] dark:text-[#f1f5f9] focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
            >
              {VOICE_OPTIONS[effectiveModelType]?.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-4 border-t border-black/[0.06] dark:border-[#2a2f45] flex-shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-[#334155] dark:text-[#cbd5e1] hover:bg-[#f1f5f9] dark:hover:bg-[#0d1117] rounded-lg transition-colors border border-black/10 dark:border-[#3b4264]"
          >
            {t('common.cancel')}
          </button>
          <button
            onClick={handleSave}
            className="px-4 py-2 text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 dark:bg-purple-600 dark:hover:bg-purple-500 rounded-lg transition-colors dark:shadow-[0_0_20px_rgba(139,92,246,0.15)]"
          >
            {t('common.save')}
          </button>
        </div>
      </div>
    </div>
  );
}
