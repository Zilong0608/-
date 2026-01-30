import React, { useState, useRef, useEffect } from "react";
import {
  ChevronDown,
  ArrowRight,
  Command,
  Cpu,
  Zap,
  Mic,
  Square,
  SkipForward,
  MessageSquare,
  BarChart2,
  Share2,
  RefreshCw,
  Home,
  X,
  Check,
  Eye,
  EyeOff,
  Send,
  ChevronUp
} from "lucide-react";
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from 'recharts';
import { motion, AnimatePresence } from "motion/react";

type AppState = "setup" | "interview" | "report";

type ReportDetail = {
  question: string;
  user_answer: string;
  total_score: number;
  llm_answer: string;
  weaknesses?: string[];
  suggestions?: string[];
};

type ReportPayload = {
  session_id: string;
  overall_score: number;
  avg_technical_accuracy: number;
  avg_clarity: number;
  avg_depth_breadth: number;
  correct_rate: number;
  weak_areas: string[];
  strong_areas: string[];
  suggestions: string[];
  details?: ReportDetail[];
};

const API_BASE = "/api/v1";
const MAX_QUESTIONS = 10;

// --- Custom Components ---

// 1. Silky Smooth Custom Select Component
interface CustomSelectProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { label: string; value: string; desc?: string }[];
  icon: React.ElementType;
}

const CustomSelect: React.FC<CustomSelectProps> = ({ label, value, onChange, options, icon: Icon }) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selectedOption = options.find(opt => opt.value === value);
  const displayLabel = selectedOption?.label.split(' - ')[0] || value;

  return (
    <div className="space-y-1.5 relative" ref={containerRef}>
      <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest pl-1">{label}</label>
      
      <div className="relative">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className={`w-full flex items-center justify-between bg-white/40 backdrop-blur-md border transition-all duration-300 rounded-xl px-4 py-3 text-sm font-medium text-slate-700 shadow-sm hover:bg-white/60 ${isOpen ? 'border-indigo-400/50 ring-2 ring-indigo-500/10' : 'border-white/60 hover:border-white'}`}
        >
          <div className="flex items-center gap-3">
            <Icon className={`w-4 h-4 ${isOpen ? 'text-indigo-500' : 'text-slate-500'} transition-colors`} />
            <span className="truncate">{displayLabel}</span>
          </div>
          <motion.div
            animate={{ rotate: isOpen ? 180 : 0 }}
            transition={{ duration: 0.2 }}
          >
            <ChevronDown className="w-4 h-4 text-slate-400" />
          </motion.div>
        </button>

        <AnimatePresence>
          {isOpen && (
            <motion.div
              initial={{ opacity: 0, y: -10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.95 }}
              transition={{ type: "spring", stiffness: 300, damping: 25 }}
              className="absolute top-full left-0 right-0 mt-2 z-50 overflow-hidden rounded-xl bg-white/90 backdrop-blur-2xl border border-white/60 shadow-xl ring-1 ring-black/5"
              style={{ maxHeight: '300px' }} 
            >
              <div className="p-1 overflow-y-auto custom-scrollbar" style={{ maxHeight: '290px' }}>
                {options.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => {
                      onChange(option.value);
                      setIsOpen(false);
                    }}
                    className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all mb-0.5 last:mb-0 ${
                      value === option.value 
                        ? 'bg-indigo-50 text-indigo-700' 
                        : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                       <div className="flex flex-col gap-0.5">
                          <span className={`font-medium ${value === option.value ? 'text-indigo-700' : 'text-slate-700'}`}>
                            {option.label}
                          </span>
                          {option.desc && (
                             <span className="text-xs text-slate-400 font-normal leading-relaxed">
                                {option.desc}
                             </span>
                          )}
                       </div>
                       {value === option.value && <Check className="w-3.5 h-3.5 mt-1 flex-shrink-0" />}
                    </div>
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

// --- Main App ---

export default function App() {
  const [appState, setAppState] = useState<AppState>("setup");
  const [isConfigOpen, setIsConfigOpen] = useState(false);

  // States for Page 2
  const [isQuestionRevealed, setIsQuestionRevealed] = useState(false);
  const [isTextInputOpen, setIsTextInputOpen] = useState(false);
  const [textAnswer, setTextAnswer] = useState("");

  const [config, setConfig] = useState({
    bank: "",
    persona: "",
    voice: "alloy"
  });

  const [categoryOptions, setCategoryOptions] = useState([
    { label: "全部题库", value: "" }
  ]);
  const [personaOptions, setPersonaOptions] = useState([
    { label: "随机", value: "" }
  ]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [openingText, setOpeningText] = useState("");
  const [report, setReport] = useState<ReportPayload | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [isStarting, setIsStarting] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isIntroPlaying, setIsIntroPlaying] = useState(false);
  const [isReportLoading, setIsReportLoading] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const ttsQueueRef = useRef<Promise<void>>(Promise.resolve());

  const [isRecording, setIsRecording] = useState(false);
  const [questionIndex, setQuestionIndex] = useState(0);

  useEffect(() => {
    loadCategories();
    loadPersonalities();
  }, []);

  const toggleRecording = () => {
    if (isIntroPlaying) {
      return;
    }
    setIsRecording(!isRecording);
  };

  const radarData = report
    ? [
        { subject: "技术准确性", A: Math.round((report.avg_technical_accuracy || 0) * 10), fullMark: 100 },
        { subject: "表达清晰度", A: Math.round((report.avg_clarity || 0) * 10), fullMark: 100 },
        { subject: "深度广度", A: Math.round((report.avg_depth_breadth || 0) * 10), fullMark: 100 },
        { subject: "正确率", A: Math.round((report.correct_rate || 0) * 100), fullMark: 100 }
      ]
    : [
        { subject: "技术准确性", A: 0, fullMark: 100 },
        { subject: "表达清晰度", A: 0, fullMark: 100 },
        { subject: "深度广度", A: 0, fullMark: 100 },
        { subject: "正确率", A: 0, fullMark: 100 }
      ];

  const currentCategoryLabel =
    categoryOptions.find(opt => opt.value === config.bank)?.label || "全部题库";

  const overallScoreDisplay = report ? Math.round(report.overall_score * 10) : 0;
  const strengthText = report?.strong_areas?.length ? report.strong_areas.join("；") : "暂无";
  const weaknessText = report?.weak_areas?.length ? report.weak_areas.join("；") : "暂无";
  const suggestionList = report?.suggestions?.length ? report.suggestions : [];
  const showReportContent = Boolean(report) && !isReportLoading;

  async function apiFetch(path: string, init?: RequestInit) {
    const headers: Record<string, string> = {};
    if (init?.body && !(init?.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { ...headers, ...(init?.headers || {}) }
    });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(detail || res.statusText);
    }
    return res;
  }

  const normalizeCategoryName = (name: string) => {
    if (!name) return name;
    const cleaned = name.replace(/\uFFFD/g, "").replace(/\?/g, "");
    const compact = cleaned.replace(/\s+/g, "");
    if (/机器学/.test(compact)) {
      return "机器学习";
    }
    return cleaned;
  };

  async function loadCategories() {
    try {
      const res = await apiFetch("/question-categories");
      const data = await res.json();
      const rawOptions = data.map((item: any) => ({
        label: normalizeCategoryName(item.name),
        value: item.key
      }));
      const seen = new Set<string>();
      const options = [{ label: "全部题库", value: "" }];
      rawOptions.forEach((option) => {
        if (seen.has(option.label)) {
          return;
        }
        seen.add(option.label);
        options.push(option);
      });
      setCategoryOptions(options);
    } catch (err) {
      setStatusMessage("题库分类加载失败");
    }
  }

  async function loadPersonalities() {
    try {
      const res = await apiFetch("/personalities");
      const data = await res.json();
      const options = [{ label: "随机", value: "" }, ...data.map((item: any) => ({
        label: item.name,
        value: item.name,
        desc: item.description
      }))];
      setPersonaOptions(options);
    } catch (err) {
      setStatusMessage("人格加载失败");
    }
  }

  async function speakText(text: string) {
    if (!text) return;
    const task = async () => {
      try {
        const res = await apiFetch("/tts", {
          method: "POST",
          body: JSON.stringify({
            text,
            voice: config.voice
          })
        });
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        if (!audioRef.current) {
          audioRef.current = new Audio();
        }
        audioRef.current.src = url;
        try {
          await audioRef.current.play();
        } catch (err) {
          return;
        }
        await new Promise<void>((resolve) => {
          const audio = audioRef.current;
          if (!audio) {
            resolve();
            return;
          }
          const handleDone = () => {
            audio.removeEventListener("ended", handleDone);
            audio.removeEventListener("error", handleDone);
            resolve();
          };
          audio.addEventListener("ended", handleDone);
          audio.addEventListener("error", handleDone);
        });
      } catch (err) {
        return;
      }
    };
    ttsQueueRef.current = ttsQueueRef.current.then(task).catch(() => {});
    return ttsQueueRef.current;
  }

  async function startInterview() {
    if (isStarting) return;
    try {
      setIsStarting(true);
      setIsIntroPlaying(true);
      setStatusMessage("");
      const payload = {
        job_type: "通用",
        difficulty: "进阶",
        max_questions: MAX_QUESTIONS,
        personality_name: config.persona || null,
        question_category: config.bank || null
      };
      const res = await apiFetch("/sessions", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      const session = await res.json();
      setSessionId(session.session_id);
      setReport(null);
      setQuestionIndex(0);
      setIsQuestionRevealed(false);
      setTextAnswer("");

      const startRes = await apiFetch(`/sessions/${session.session_id}/start`, { method: "POST" });
      const startData = await startRes.json();
      setOpeningText(startData.opening || "");
      setCurrentQuestion("");
      setAppState("interview");
      await speakText(startData.opening || "");
      setCurrentQuestion(startData.first_question || "");
      await speakText(startData.first_question || "");
    } catch (err) {
      setStatusMessage("启动面试失败，请检查后端是否已启动");
    } finally {
      setIsIntroPlaying(false);
      setIsStarting(false);
    }
  }

  async function submitAnswer() {
    if (isIntroPlaying) return;
    if (!sessionId) return;
    const answer = textAnswer.trim();
    if (!answer) {
      setStatusMessage("请先输入回答");
      return;
    }
    if (isSubmitting) return;
    try {
      setIsSubmitting(true);
      await apiFetch(`/sessions/${sessionId}/answer-async`, {
        method: "POST",
        body: JSON.stringify({ answer })
      });
      setTextAnswer("");
      setIsTextInputOpen(false);
      setStatusMessage("");
    } catch (err) {
      setStatusMessage("提交答案失败，请重试");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function fetchNextQuestion() {
    if (isIntroPlaying) return;
    if (!sessionId) return;
    try {
      const res = await apiFetch(`/sessions/${sessionId}/next-question`);
      const data = await res.json();
      if (!data.has_next) {
        await endInterview();
        return;
      }
      setIsQuestionRevealed(false);
      setIsRecording(false);
      setQuestionIndex(prev => prev + 1);
      setCurrentQuestion(data.question || "");
      await speakText(data.question || "");
    } catch (err) {
      setStatusMessage("获取下一题失败");
    }
  }

  async function handleNext() {
    if (isIntroPlaying) return;
    if (textAnswer.trim()) {
      await submitAnswer();
    }
    await fetchNextQuestion();
  }

  async function endInterview() {
    if (!sessionId) {
      setAppState("report");
      return;
    }
    setIsReportLoading(true);
    setReport(null);
    setAppState("report");
    try {
      const res = await apiFetch(`/sessions/${sessionId}/end`, { method: "POST" });
      const reportData = await res.json();
      setReport(reportData);
      setSessionId(null);
    } catch (err) {
      setStatusMessage("生成报告失败");
    } finally {
      setIsReportLoading(false);
    }
  }

  return (
    <div className="h-screen overflow-hidden bg-[#F8FAFC] text-slate-600 relative flex flex-col font-sans selection:bg-indigo-500/30 w-full items-center justify-center">
      
      {/* Dynamic Background */}
      
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,900;1,900&family=Playfair+Display:ital,wght@0,400;0,600;1,400&display=swap');
        .font-black-sans { font-family: 'Inter', sans-serif; font-weight: 900; }
        .font-serif-elegant { font-family: 'Playfair Display', serif; }

        @keyframes shine-text {
          0% { background-position: 200% center; }
          100% { background-position: -200% center; }
        }
        
        .animate-text-flow {
          background-size: 200% auto;
          animation: shine-text 10s linear infinite;
        }
        
        /* 彩色原子轨道 */
        .orbit {
          position: absolute;
          border-radius: 50%;
          border-width: 2px;
          border-style: solid;
          mix-blend-mode: multiply;
        }
        .orbit-cyan {
          border-color: rgba(6, 182, 212, 0.8);
          box-shadow: 0 0 12px rgba(6, 182, 212, 0.4);
        }
        .orbit-magenta {
          border-color: rgba(236, 72, 153, 0.8);
          box-shadow: 0 0 12px rgba(236, 72, 153, 0.4);
        }
        .orbit-yellow {
          border-color: rgba(234, 179, 8, 0.8);
          box-shadow: 0 0 12px rgba(234, 179, 8, 0.4);
        }
        
        /* 全彩核心 - 液体宝石质感 */
        .atom-core {
          background: radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.9) 0%, rgba(244, 114, 182, 0.2) 20%, rgba(192, 132, 252, 0.8) 50%, rgba(96, 165, 250, 0.8) 80%, rgba(79, 70, 229, 0.9) 100%);
          box-shadow: 
            inset -4px -4px 10px rgba(79, 70, 229, 0.5),
            inset 4px 4px 10px rgba(255, 255, 255, 0.8),
            0 0 20px rgba(168, 85, 247, 0.5),
            0 0 40px rgba(59, 130, 246, 0.3);
        }
        .atom-core-inner {
            position: absolute;
            inset: 0;
            border-radius: 50%;
            background: linear-gradient(135deg, #f472b6, #22d3ee, #fbbf24);
            filter: blur(8px);
            opacity: 0.6;
            animation: hue-flow 6s infinite alternate;
        }

        /* 呼吸动画 */
        @keyframes breathe {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.05); }
        }
        .animate-breathe {
          animation: breathe 4s ease-in-out infinite;
        }

        @keyframes hue-flow {
            0% { filter: blur(8px) hue-rotate(0deg); transform: scale(0.9); }
            100% { filter: blur(8px) hue-rotate(90deg); transform: scale(1.1); }
        }

        /* 液态变形动画 - 极度扭曲与尖角突起 (说话时) */
        @keyframes morph-deep {
          0% { border-radius: 50%; transform: scale(1) rotate(0deg); }
          
          /* 阶段1: 左上角剧烈凸起 (类似水滴将滴未滴) */
          33% { 
            border-radius: 20% 80% 40% 60% / 30% 80% 40% 70%; 
            transform: scale(1.1) translate(-5px, -5px) rotate(-15deg); 
          }
          
          /* 阶段2: 此时右下和左下同时受力，挤压成扁平状 */
          66% { 
            border-radius: 70% 30% 20% 80% / 60% 30% 80% 40%; 
            transform: scale(0.95) translate(5px, 5px) rotate(10deg); 
          }
          
          /* 阶段3: 四角拉伸，极不规则 */
          85% {
            border-radius: 35% 65% 25% 75% / 65% 25% 75% 25%;
            transform: scale(1.15) rotate(5deg);
          }

          100% { border-radius: 50%; transform: scale(1) rotate(0deg); }
        }

        /* 内部核心冲撞 - 大幅度顶撞外壁 */
        @keyframes inner-push {
          0% { transform: translate(0, 0) scale(1); }
          33% { transform: translate(-25px, -20px) scale(1.1); } /* 配合左上角凸起 */
          66% { transform: translate(20px, 25px) scale(0.9); }  /* 配合右下挤压 */
          85% { transform: translate(-15px, 20px) scale(1.2); } /* 再次突围 */
          100% { transform: translate(0, 0) scale(1); }
        }

        .animate-morph-deep {
          animation: morph-deep 1.5s ease-in-out infinite alternate;
        }
        
        .animate-inner-push {
           animation: inner-push 1.5s ease-in-out infinite alternate;
        }

        @keyframes orbit-spin {
          0% { transform: rotate3d(1, 1, 1, 0deg); }
          100% { transform: rotate3d(1, 1, 1, 360deg); }
        }
        @keyframes orbit-spin-2 {
          0% { transform: rotate3d(1, -1, 0, 0deg); }
          100% { transform: rotate3d(1, -1, 0, 360deg); }
        }
        @keyframes orbit-spin-3 {
          0% { transform: rotate3d(0, 1, 1, 0deg); }
          100% { transform: rotate3d(0, 1, 1, 360deg); }
        }

        .animate-orbit-1 { animation: orbit-spin 3s linear infinite; }
        .animate-orbit-2 { animation: orbit-spin-2 4s linear infinite; }
        .animate-orbit-3 { animation: orbit-spin-3 5s linear infinite; }
        
        @keyframes blob {
          0% { transform: translate(0px, 0px) scale(1); }
          33% { transform: translate(30px, -50px) scale(1.1); }
          66% { transform: translate(-20px, 20px) scale(0.9); }
          100% { transform: translate(0px, 0px) scale(1); }
        }
        .animate-blob {
          animation: blob 10s infinite;
        }
        .animation-delay-2000 {
          animation-delay: 2s;
        }
        .animation-delay-4000 {
          animation-delay: 4s;
        }
        .custom-scrollbar::-webkit-scrollbar {
          width: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: #cbd5e1;
          border-radius: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: #94a3b8;
        }
      `}</style>

      <svg className="hidden">
        <defs>
          <filter id="water" x="-20%" y="-20%" width="140%" height="140%">
            <feTurbulence type="fractalNoise" baseFrequency="0.005 0.01" numOctaves="1" result="noise">
              <animate attributeName="baseFrequency" dur="10s" values="0.005 0.01; 0.005 0.02; 0.005 0.01" repeatCount="indefinite" />
            </feTurbulence>
            <feDisplacementMap in="SourceGraphic" in2="noise" scale="4" />
          </filter>
        </defs>
      </svg>

      {/* 背景：全彩极光 */}
      <div className="absolute inset-0 bg-[#f8fafc]">
        {/* Purple/Pink Blob */}
        <div className="absolute top-[-20%] left-[10%] w-[70vw] h-[70vw] bg-purple-300/40 rounded-full blur-[100px] mix-blend-multiply animate-blob" />
        {/* Cyan/Blue Blob */}
        <div className="absolute top-[-10%] right-[10%] w-[60vw] h-[60vw] bg-cyan-300/40 rounded-full blur-[100px] mix-blend-multiply animate-blob animation-delay-2000" />
        {/* Warm Orange/Rose Blob */}
        <div className="absolute bottom-[-20%] left-[30%] w-[60vw] h-[60vw] bg-rose-300/40 rounded-full blur-[100px] mix-blend-multiply animate-blob animation-delay-4000" />
        <div className="absolute inset-0 opacity-[0.03] bg-[url('https://grainy-gradients.vercel.app/noise.svg')]" />
      </div>

      {appState === "setup" && (
        <div className="relative z-10 w-full h-full max-w-4xl px-4 flex flex-col items-center justify-between min-h-[80vh]">
          
          {/* Header */}
          <motion.div 
            className="relative flex flex-col items-center mt-12 md:mt-20"
            layoutId="header"
          >
            {/* 本体 - 文字流光优化 */}
            <div className="flex items-center gap-6 md:gap-8 select-none z-10 relative">
              <span className="font-black-sans italic -skew-x-6 text-5xl md:text-7xl tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-slate-900 via-slate-600 to-slate-900 animate-text-flow pr-2">
                MirrorCareer
              </span>
              <div className="h-10 md:h-14 w-[1px] bg-gradient-to-b from-purple-400 to-cyan-400 transform rotate-[15deg] opacity-60"></div>
              {/* Interviewer 颜色改为更协调的紫/青柔和渐变 */}
              <span className="font-serif-elegant italic text-5xl md:text-7xl tracking-normal text-transparent bg-clip-text bg-gradient-to-r from-indigo-500 via-purple-500 to-indigo-500 animate-text-flow">
                interviewer
              </span>
            </div>

            {/* 倒影 */}
            <div 
              className="absolute top-[60%] left-0 right-0 flex items-center justify-center gap-6 md:gap-8 select-none pointer-events-none opacity-20 origin-top transform scale-y-[-0.8]"
              style={{
                filter: 'url(#water)',
                maskImage: 'linear-gradient(to bottom, rgba(0,0,0,0.8), transparent 70%)',
                WebkitMaskImage: 'linear-gradient(to bottom, rgba(0,0,0,0.8), transparent 70%)',
              }}
              aria-hidden="true"
            >
               <span className="font-black-sans italic -skew-x-6 text-5xl md:text-7xl text-slate-800 tracking-tighter pr-2">
                MirrorCareer
              </span>
              <div className="h-10 md:h-14 w-[1px] bg-slate-400 transform rotate-[15deg]"></div>
              <span className="font-serif-elegant italic text-5xl md:text-7xl text-slate-800 tracking-normal">
                interviewer
              </span>
            </div>

            <div className="mt-16 flex items-center gap-3 text-[10px] font-bold tracking-[0.3em] text-slate-400 uppercase opacity-60">
              <span className="w-6 h-[1px] bg-slate-300"></span>
              <span>AI Simulation System v2.0</span>
              <span className="w-6 h-[1px] bg-slate-300"></span>
            </div>
          </motion.div>

          {/* Interaction Area */}
          <div className="flex flex-col items-center justify-end w-full pb-16 relative h-[500px]">
            
            {/* The Panel - Ejection Animation */}
            <AnimatePresence>
              {isConfigOpen && (
                <motion.div
                  key="config-panel"
                  className="absolute bottom-32 w-full max-w-2xl z-20"
                  initial={{ 
                    opacity: 0, 
                    scaleX: 0.1,     
                    scaleY: 0.1,     
                    y: 150,          
                    filter: "blur(20px)" 
                  }}
                  animate={{ 
                    opacity: 1, 
                    scaleX: 1, 
                    scaleY: 1, 
                    y: 0, 
                    filter: "blur(0px)" 
                  }}
                  exit={{ 
                    opacity: 0, 
                    scaleX: 0.1,     
                    scaleY: 0.1,     
                    y: 150,          
                    filter: "blur(20px)",
                    transition: { duration: 0.4, ease: "backIn" }
                  }}
                  transition={{ 
                    type: "spring", 
                    damping: 18, 
                    stiffness: 120,
                    mass: 0.8
                  }}
                  style={{ transformOrigin: "bottom center" }}
                >
                  {/* Panel Content - Ultimate Glassmorphism */}
                  <div className="group relative bg-white/30 backdrop-blur-3xl rounded-[2.5rem] border border-white/40 shadow-[0_30px_60px_-10px_rgba(100,100,100,0.1)] p-2 ring-1 ring-white/60">
                    <div className="bg-white/20 rounded-[2rem] p-8 space-y-6">
                      
                      <div className="space-y-4">
                        <CustomSelect 
                          label="题库分类"
                          value={config.bank}
                          onChange={(v) => setConfig(prev => ({ ...prev, bank: v }))}
                          icon={Command}
                          options={categoryOptions}
                        />
                        
                        <CustomSelect 
                          label="面试官人格"
                          value={config.persona}
                          onChange={(v) => setConfig(prev => ({ ...prev, persona: v }))}
                          icon={Cpu}
                          options={personaOptions}
                        />
                        
                        <CustomSelect 
                          label="声音"
                          value={config.voice}
                          onChange={(v) => setConfig(prev => ({ ...prev, voice: v }))}
                          icon={Zap}
                          options={[
                            { label: "alloy", value: "alloy" },
                            { label: "echo", value: "echo" },
                            { label: "fable", value: "fable" },
                            { label: "onyx", value: "onyx" },
                            { label: "nova", value: "nova" },
                            { label: "shimmer", value: "shimmer" },
                            { label: "coral", value: "coral" },
                            { label: "verse", value: "verse" },
                            { label: "ballad", value: "ballad" },
                            { label: "ash", value: "ash" },
                            { label: "sage", value: "sage" },
                            { label: "marin", value: "marin" },
                            { label: "cedar", value: "cedar" }
                          ]}
                        />
                      </div>

                      <button 
                        onClick={startInterview}
                        disabled={isStarting}
                        className="group relative w-full overflow-hidden rounded-xl bg-slate-900 py-3.5 mt-2 transition-all hover:scale-[1.01] active:scale-[0.99] shadow-xl shadow-indigo-900/10"
                      >
                        {/* 按钮背景 - 极光流转 */}
                        <div className="absolute inset-0 bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 opacity-100" />
                        <div className="absolute inset-0 bg-gradient-to-r from-purple-500/20 via-cyan-500/20 to-purple-500/20 opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                        
                        <div className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
                            <div className="h-full w-full bg-gradient-to-r from-transparent via-white/10 to-transparent skew-x-12 translate-x-[-100%] group-hover:animate-shine" />
                        </div>
                        <div className="relative flex items-center justify-center gap-2 text-white font-medium text-sm tracking-wide">
                          <span>Start</span>
                          <ArrowRight className="w-4 h-4" />
                        </div>
                      </button>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* The Colorful Atom Orb */}
            <motion.div
               className="relative z-30 cursor-pointer group"
               onClick={() => setIsConfigOpen(!isConfigOpen)}
               animate={isConfigOpen ? { y: 20, scale: 0.8 } : { y: 0, scale: 1 }}
               transition={{ type: "spring", stiffness: 300, damping: 20 }}
            >
               <div className="relative w-24 h-24 flex items-center justify-center">
                  
                  {/* Orbits */}
                  <div className={`orbit orbit-cyan w-24 h-24 animate-orbit-1 ${isConfigOpen ? 'opacity-30' : 'opacity-100'}`} />
                  <div className={`orbit orbit-magenta w-20 h-20 animate-orbit-2 ${isConfigOpen ? 'opacity-30' : 'opacity-100'}`} />
                  <div className={`orbit orbit-yellow w-22 h-22 animate-orbit-3 ${isConfigOpen ? 'opacity-30' : 'opacity-100'}`} />

                  {/* Core */}
                  <div className="w-8 h-8 relative z-10 transition-all duration-500 group-hover:scale-110">
                    <div className="atom-core w-full h-full rounded-full relative overflow-hidden">
                       <div className="atom-core-inner"></div>
                    </div>
                     {isConfigOpen && (
                        <div className="absolute inset-0 flex items-center justify-center z-20">
                           <X className="w-4 h-4 text-white drop-shadow-md" />
                        </div>
                     )}
                  </div>
                  
                  {/* Glow */}
                  {!isConfigOpen && (
                     <div className="absolute w-12 h-12 bg-gradient-to-r from-purple-500/20 to-cyan-500/20 rounded-full animate-ping z-0" />
                  )}

               </div>

               {/* Hint Text */}
               {!isConfigOpen && (
                  <motion.div 
                     initial={{ opacity: 0, y: 10 }}
                     animate={{ opacity: 1, y: 0 }}
                     transition={{ delay: 0.2 }}
                     className="absolute -bottom-2 left-1/2 -translate-x-1/2 whitespace-nowrap text-[10px] font-bold tracking-[0.3em] text-slate-400 uppercase opacity-60"
                  >
                     Start
                  </motion.div>
               )}
            </motion.div>

          </div>
        </div>
      )}

      {/* PAGE 2: Interview */}
      {appState === "interview" && (
        <div className="relative z-10 w-full h-full flex flex-col animate-in fade-in duration-700 overflow-hidden">
           
           <header className="px-8 py-4 flex items-center justify-between shrink-0">
              <button 
                onClick={() => setAppState("setup")}
                className="text-slate-400 hover:text-slate-800 transition-colors text-sm font-medium flex items-center gap-2"
              >
                 <span className="w-8 h-8 rounded-full bg-white/50 flex items-center justify-center border border-white/60">
                    <ArrowRight className="w-4 h-4 rotate-180" />
                 </span>
                 退出面试
              </button>
              
              <div className="flex items-center gap-3">
                 <div className="px-3 py-1.5 rounded-full bg-white/40 border border-white/50 backdrop-blur-md text-xs font-semibold text-slate-600 flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
                    Live Session
                 </div>
                 <div className="px-3 py-1.5 rounded-full bg-white/40 border border-white/50 backdrop-blur-md text-xs font-semibold text-slate-600">
                    {currentCategoryLabel} / Q{questionIndex + 1}
                 </div>
              </div>
           </header>

           <main className="flex-1 flex flex-col items-center justify-between relative w-full max-w-4xl mx-auto px-6 overflow-hidden min-h-0">
              
              {/* Question Area - Revised */}
              <div className="w-full mt-2 mb-2 flex flex-col items-center relative z-20 shrink-0">
                 {/* The Small Trigger Button */}
                 <button 
                    onClick={() => setIsQuestionRevealed(!isQuestionRevealed)}
                    disabled={isIntroPlaying}
                    className={`bg-white/60 backdrop-blur-md border border-white/60 px-6 py-2 rounded-full shadow-sm text-xs font-bold tracking-widest text-slate-500 uppercase transition-all flex items-center gap-2 hover:bg-white/80 hover:text-indigo-600 hover:border-indigo-200 ${isQuestionRevealed ? 'mb-4' : ''}`}
                 >
                    Current Question
                    <motion.div animate={{ rotate: isQuestionRevealed ? 180 : 0 }}>
                       <ChevronDown className="w-3 h-3" />
                    </motion.div>
                 </button>

                 {/* The Revealed Card */}
                 <AnimatePresence>
                    {isQuestionRevealed && (
                       <motion.div
                          initial={{ opacity: 0, y: -20, scale: 0.95, height: 0 }}
                          animate={{ opacity: 1, y: 0, scale: 1, height: "auto" }}
                          exit={{ opacity: 0, y: -20, scale: 0.95, height: 0 }}
                          transition={{ type: "spring", stiffness: 300, damping: 25 }}
                          className="w-full overflow-hidden"
                       >
                          <div className="relative bg-white/60 backdrop-blur-xl border border-white/60 p-6 md:p-8 rounded-[2rem] shadow-[0_20px_50px_-12px_rgba(0,0,0,0.1)] text-center group max-h-[30vh] overflow-y-auto custom-scrollbar">
                             <div className="absolute inset-0 rounded-[2rem] bg-gradient-to-r from-purple-200/50 via-cyan-200/50 to-yellow-200/50 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
                             
                             <h2 className="relative z-10 text-xl md:text-2xl font-medium text-slate-800 leading-relaxed font-grotesk">
                                “{currentQuestion || "暂无问题"}”
                             </h2>
                          </div>
                       </motion.div>
                    )}
                 </AnimatePresence>
              </div>

              {/* CENTER INTERACTION AREA - Orb vs Text Input Switch */}
              <div className="relative flex-1 flex items-center justify-center w-full min-h-0">
                 
                 <AnimatePresence mode="wait">
                    {/* MODE 1: Text Input Overlay */}
                    {isTextInputOpen ? (
                       <motion.div
                          key="text-input"
                          initial={{ opacity: 0, scale: 0.9, y: 20, filter: "blur(10px)" }}
                          animate={{ opacity: 1, scale: 1, y: 0, filter: "blur(0px)" }}
                          exit={{ opacity: 0, scale: 0.9, y: 20, filter: "blur(10px)" }}
                          transition={{ type: "spring", stiffness: 300, damping: 25 }}
                          className="absolute z-30 w-full max-w-xl"
                       >
                          {/* Crystal Glass Card */}
                          <div className="relative bg-white/30 backdrop-blur-3xl border border-white/40 shadow-[0_40px_80px_-20px_rgba(0,0,0,0.15)] rounded-[2.5rem] p-6 md:p-8 overflow-hidden group">
                             
                             {/* Glossy Sheen Effect */}
                             <div className="absolute top-0 left-0 w-full h-1/2 bg-gradient-to-b from-white/40 to-transparent pointer-events-none" />
                             <div className="absolute -top-24 -right-24 w-48 h-48 bg-purple-400/20 rounded-full blur-[50px] pointer-events-none" />
                             <div className="absolute -bottom-24 -left-24 w-48 h-48 bg-cyan-400/20 rounded-full blur-[50px] pointer-events-none" />

                             <div className="relative z-10">
                                <div className="flex justify-between items-center mb-4 pl-1">
                                   <div className="flex items-center gap-2">
                                      <div className="w-1 h-4 bg-gradient-to-b from-indigo-400 to-purple-400 rounded-full" />
                                      <h3 className="text-sm font-bold text-slate-600 uppercase tracking-widest">Type Answer</h3>
                                   </div>
                                   <button 
                                      onClick={() => setIsTextInputOpen(false)} 
                                      className="w-8 h-8 rounded-full bg-white/20 hover:bg-white/40 border border-white/30 flex items-center justify-center transition-all hover:rotate-90 text-slate-500 hover:text-slate-800"
                                   >
                                      <X className="w-4 h-4" />
                                   </button>
                                </div>
                                
                                <div className="relative group/input">
                                   <textarea 
                                      className="w-full h-32 md:h-40 bg-white/20 hover:bg-white/30 focus:bg-white/40 border border-white/30 rounded-2xl p-4 md:p-5 text-slate-700 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-300 outline-none resize-none placeholder:text-slate-400/80 text-sm md:text-base leading-relaxed transition-all shadow-inner"
                                      placeholder="在这块水晶上书写你的想法..."
                                      value={textAnswer}
                                      onChange={(e) => setTextAnswer(e.target.value)}
                                      autoFocus
                                      style={{ textShadow: '0 1px 1px rgba(255,255,255,0.5)' }}
                                   />
                                   {/* Corner accents */}
                                   <div className="absolute bottom-3 right-3 text-[10px] font-bold text-slate-400/60 pointer-events-none uppercase tracking-widest">
                                      Markdown Support
                                   </div>
                                </div>

                                <div className="flex justify-end gap-3 mt-5">
                                   <button 
                                     onClick={() => setIsTextInputOpen(false)}
                                     className="px-5 py-2 rounded-xl text-slate-500 hover:text-slate-700 font-medium text-xs md:text-sm transition-colors hover:bg-white/20"
                                   >
                                     Cancel
                                   </button>
                                   <button 
                                     onClick={submitAnswer}
                                     disabled={isIntroPlaying || isSubmitting}
                                     className="relative overflow-hidden px-6 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl font-medium text-xs md:text-sm flex items-center gap-2 shadow-xl shadow-slate-900/20 transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
                                   >
                                     {/* Inner sheen for button */}
                                     <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent translate-x-[-100%] hover:animate-shine" />
                                     <span>Submit Answer</span>
                                     <Send className="w-3.5 h-3.5" />
                                   </button>
                                </div>
                             </div>
                          </div>
                       </motion.div>
                    ) : (
                       /* MODE 2: Living Orb */
                       <motion.div
                          key="orb"
                          initial={{ opacity: 0, scale: 0.8 }}
                          animate={{ opacity: 1, scale: 1 }}
                          exit={{ opacity: 0, scale: 0.8 }}
                          className={`cursor-pointer transition-transform active:scale-95 relative z-10 ${isIntroPlaying ? "pointer-events-none opacity-60" : ""}`}
                          onClick={isIntroPlaying ? undefined : toggleRecording}
                       >
                          {/* Pulsating Rings when active */}
                          {isRecording && (
                             <>
                               <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-60 h-60 border border-purple-400/30 rounded-full animate-ping" />
                               <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-80 h-80 border border-cyan-400/20 rounded-full animate-ping animation-delay-2000" />
                             </>
                          )}

                          {/* Living Core - Flat Glass Style (Restored Color, Faster Speed) */}
                          <div className="relative w-48 h-48 flex items-center justify-center">
                               {/* 外部光晕 */}
                               <div className={`absolute inset-0 bg-gradient-to-r from-purple-500/30 to-cyan-500/30 blur-2xl transition-all duration-300 ${isRecording ? 'opacity-100 scale-125' : 'opacity-40 scale-100'}`} />
                               
                               {/* Core Body - 恢复之前的通透材质，但去除立体高光和内阴影 */}
                               <div 
                                  className={`w-40 h-40 relative overflow-hidden transition-all duration-500 backdrop-blur-md border
                                    ${isRecording 
                                        ? 'animate-morph-deep border-rose-200/40 bg-rose-500/20 shadow-[0_0_40px_rgba(244,63,94,0.4)]' 
                                        : 'rounded-full animate-breathe border-white/30 bg-white/10 shadow-[0_0_30px_rgba(168,85,247,0.2)]'
                                    }
                                  `}
                               >
                                  {/* 内部流动的色彩 - 恢复 mix-blend-overlay 的高级质感 */}
                                  <div className={`absolute inset-0 opacity-80 mix-blend-overlay bg-gradient-to-br from-cyan-300 via-purple-400 to-rose-400 transition-transform duration-500 ${isRecording ? 'scale-150 animate-[spin_2s_linear_infinite]' : 'scale-100 rotate-0'}`}></div>
                                  
                                  {/* 内部冲撞的能量体 */}
                                  {isRecording && (
                                     <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-28 h-28 bg-gradient-to-tr from-white to-rose-300 rounded-full blur-xl mix-blend-overlay animate-inner-push" />
                                  )}
                                  
                                  {/* 已移除高光层 (Highlight Div) 以保持平面感 */}
                               </div>
                               
                               {/* Icon Overlay */}
                               <div className="absolute inset-0 flex items-center justify-center text-white drop-shadow-md z-20 pointer-events-none transition-all duration-500">
                                  {isRecording ? (
                                     <div className="flex gap-1.5 items-end h-10 pb-1">
                                        <div className="w-2 bg-white rounded-full animate-[bounce_0.8s_infinite] h-5" />
                                        <div className="w-2 bg-white rounded-full animate-[bounce_0.8s_infinite_0.2s] h-10" />
                                        <div className="w-2 bg-white rounded-full animate-[bounce_0.8s_infinite_0.4s] h-6" />
                                     </div>
                                  ) : (
                                     <Mic className="w-10 h-10 opacity-60 mix-blend-overlay" />
                                  )}
                               </div>
                          </div>
                          
                          <div className={`absolute -bottom-16 left-1/2 -translate-x-1/2 whitespace-nowrap transition-all duration-500 ${isRecording ? 'opacity-0 translate-y-2' : 'opacity-100 translate-y-0'}`}>
                             <span className="text-slate-400 text-sm font-medium tracking-wide">点击核心开始回答</span>
                          </div>
                       </motion.div>
                    )}
                 </AnimatePresence>
                 
              </div>

              <div className="w-full pb-8 md:pb-10 grid grid-cols-1 md:grid-cols-3 gap-6 items-center shrink-0">
                 
                 {/* Unified Glass Button Style */}
                 <div className="flex justify-center md:justify-start">
                    <button 
                      onClick={() => setIsTextInputOpen(true)}
                      disabled={isIntroPlaying}
                      className={`flex items-center gap-2 px-6 py-3 rounded-xl bg-white/40 border border-white/50 hover:bg-white/60 text-slate-700 transition-all text-sm font-medium shadow-sm hover:shadow-md group ${isTextInputOpen ? 'opacity-0 pointer-events-none' : 'opacity-100'}`}
                    >
                       <MessageSquare className="w-4 h-4 group-hover:scale-110 transition-transform" />
                       切换文字输入
                    </button>
                 </div>

                 <div className="flex justify-center">
                    <button 
                      onClick={toggleRecording}
                      disabled={isTextInputOpen || isIntroPlaying}
                      className={`flex items-center gap-2 px-6 py-3 rounded-xl transition-all text-sm font-medium shadow-sm hover:shadow-md group 
                        ${isTextInputOpen ? 'opacity-0 scale-90 pointer-events-none' : 'opacity-100 scale-100'} 
                        ${isIntroPlaying ? 'opacity-50 pointer-events-none' : ''}
                        ${isRecording 
                          ? 'bg-rose-50/50 border border-rose-200 text-rose-600 hover:bg-rose-100/60' 
                          : 'bg-white/40 border border-white/50 hover:bg-white/60 text-slate-700'
                        }`}
                    >
                       {isRecording ? (
                         <>
                           <Square className="w-4 h-4 fill-current" />
                           停止回答
                           <span className="relative flex h-2 w-2 ml-1">
                              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                              <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
                            </span>
                         </>
                       ) : (
                         <>
                           <Mic className="w-4 h-4" />
                           开始回答
                         </>
                       )}
                    </button>
                 </div>

                 <div className="flex justify-center md:justify-end">
                    <button 
                      onClick={handleNext}
                      disabled={isIntroPlaying}
                      className="flex items-center gap-2 px-6 py-3 rounded-xl bg-white/40 border border-white/50 hover:bg-white/60 text-slate-700 transition-all text-sm font-medium shadow-sm hover:shadow-md group disabled:opacity-60 disabled:cursor-not-allowed"
                    >
                       {questionIndex < MAX_QUESTIONS - 1 ? '跳过/下一题' : '完成面试'}
                       <SkipForward className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                    </button>
                 </div>

              </div>
           </main>
        </div>
      )}

      {appState === "report" && (
         <div className="relative z-10 w-full h-screen flex flex-col animate-in fade-in slide-in-from-bottom-8 duration-700 overflow-hidden">
            <header className="px-8 py-6 flex items-center justify-between shrink-0">
               <div className="flex items-center gap-2">
                 <div className="w-8 h-8 bg-gradient-to-br from-purple-500 to-indigo-600 rounded-lg flex items-center justify-center text-white shadow-lg shadow-indigo-500/20">
                   <BarChart2 className="w-4 h-4" />
                 </div>
                 <span className="font-semibold text-slate-800">Interview Report</span>
               </div>
               
               <div className="flex gap-2">
                 <button 
                    onClick={() => { setAppState("setup"); setQuestionIndex(0); setIsConfigOpen(false); }}
                    className="p-2 hover:bg-white/50 rounded-full transition-colors text-slate-600"
                    title="Home"
                  >
                    <Home className="w-5 h-5" />
                 </button>
               </div>
            </header>

            <main className="flex-1 w-full max-w-6xl mx-auto px-6 pb-12 grid grid-cols-1 md:grid-cols-12 gap-6 overflow-hidden min-h-0">
                {!showReportContent && (
                  <div className="md:col-span-12 bg-white/60 backdrop-blur-xl border border-white/60 p-10 rounded-[2rem] shadow-sm text-center">
                     <div className="text-slate-500 font-medium mb-3">正在生成测评...</div>
                     <div className="w-full h-2 bg-slate-200/60 rounded-full overflow-hidden">
                        <div className="h-full w-1/3 bg-gradient-to-r from-indigo-500 via-purple-500 to-indigo-500 animate-pulse" />
                     </div>
                  </div>
                )}

                <div className={showReportContent ? "contents" : "hidden"}>
                {/* Left Column: Summary & Chart */}
                <div className="md:col-span-5 space-y-6 flex flex-col min-h-0">
                   {/* Score Card */}
                   <div className="bg-white/60 backdrop-blur-xl border border-white/60 p-8 rounded-[2rem] shadow-sm relative overflow-hidden group">
                      <div className="absolute top-0 right-0 p-8 opacity-10 pointer-events-none group-hover:scale-110 transition-transform duration-700">
                         <BarChart2 className="w-32 h-32 text-indigo-500" />
                      </div>
                      <div className="relative z-10">
                        <div className="text-slate-500 font-medium mb-1 uppercase tracking-wider text-xs">Overall Score</div>
                        <div className="flex items-baseline gap-2">
                          <span className="text-7xl font-black text-transparent bg-clip-text bg-gradient-to-r from-indigo-600 to-purple-600 tracking-tighter">{overallScoreDisplay}</span>
                          <span className="text-xl text-slate-400 font-medium">/ 100</span>
                        </div>
                        <div className="mt-4 inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-100 text-emerald-700 text-xs font-bold uppercase">
                           <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                           Strong Candidate
                        </div>
                      </div>
                   </div>

                   {/* Radar Chart Card */}
                   <div className="bg-white/60 backdrop-blur-xl border border-white/60 p-6 rounded-[2rem] shadow-sm flex-1 min-h-[400px] flex flex-col">
                      <h3 className="text-lg font-semibold text-slate-800 mb-6 px-2">Competency Radar</h3>
                      <div className="flex-1 w-full h-full min-h-[300px] relative">
                        <ResponsiveContainer width="100%" height="100%">
                          <RadarChart cx="50%" cy="50%" outerRadius="70%" data={radarData}>
                            <PolarGrid stroke="#e2e8f0" />
                            <PolarAngleAxis dataKey="subject" tick={{ fill: '#64748b', fontSize: 12, fontWeight: 600 }} />
                            <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                            <Radar
                              name="Candidate"
                              dataKey="A"
                              stroke="#8b5cf6"
                              strokeWidth={3}
                              fill="#a78bfa"
                              fillOpacity={0.4}
                            />
                          </RadarChart>
                        </ResponsiveContainer>
                      </div>
                   </div>
                </div>

                {/* Right Column: Detailed Feedback */}
                <div className="md:col-span-7 space-y-6 min-h-0">
                   <div className="bg-white/60 backdrop-blur-xl border border-white/60 p-8 rounded-[2rem] shadow-sm h-full flex flex-col min-h-0">
                      <h3 className="text-lg font-semibold text-slate-800 mb-6">Detailed Feedback</h3>
                      
                      <div className="space-y-8 overflow-y-auto pr-2 custom-scrollbar flex-1">
                         <div className="space-y-3">
                            <h4 className="text-sm font-bold text-indigo-600 uppercase tracking-widest flex items-center gap-2">
                               <div className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                               Strengths
                            </h4>
                            <p className="text-slate-600 leading-relaxed">{strengthText}</p>
                            <p className="text-slate-600 leading-relaxed hidden">
                               候选人在 <strong>React 原理</strong> 方面展现了深刻的理解，能够清晰解释 Virtual DOM 的 Diff 算法及其优化策略。同时，在<strong>系统设计</strong>环节，对于高并发场景下的缓存策略和数据库锁机制有独到的见解，显示出良好的工程落地能力。
                            </p>
                         </div>

                         <div className="w-full h-px bg-slate-200/60" />

                         <div className="space-y-3">
                            <h4 className="text-sm font-bold text-amber-600 uppercase tracking-widest flex items-center gap-2">
                               <div className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                               Areas for Improvement
                            </h4>
                            <p className="text-slate-600 leading-relaxed">{weaknessText}</p>
                            <p className="text-slate-600 leading-relaxed hidden">
                               在回答<strong>闭包</strong>相关问题时，虽然理论定义准确，但在结合实际业务场景（如 Hooks 实现原理或防抖节流）的举例上略显生硬。建议多结合源码阅读来加深对 JS 底层机制的理解。
                            </p>
                         </div>

                         <div className="w-full h-px bg-slate-200/60" />

                         <div className="space-y-3">
                            <h4 className="text-sm font-bold text-emerald-600 uppercase tracking-widest flex items-center gap-2">
                               <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                               Actionable Advice
                            </h4>
                            <ul className="space-y-2 text-slate-600">
                               {suggestionList.length ? (
                                 suggestionList.map((item, index) => (
                                   <li key={`${index}-${item}`} className="flex items-start gap-2">
                                      <span className="text-emerald-500 font-bold mt-1">{index + 1}.</span>
                                      <span>{item}</span>
                                   </li>
                                 ))
                               ) : (
                                 <li className="flex items-start gap-2">
                                    <span className="text-emerald-500 font-bold mt-1">1.</span>
                                    <span>暂无</span>
                                 </li>
                               )}
                            </ul>
                            <ul className="space-y-2 text-slate-600 hidden">
                               <li className="flex items-start gap-2">
                                  <span className="text-emerald-500 font-bold mt-1">1.</span>
                                  <span>深入学习浏览器渲染原理，特别是 Composite 和 Layer 的概念。</span>
                               </li>
                               <li className="flex items-start gap-2">
                                  <span className="text-emerald-500 font-bold mt-1">2.</span>
                                  <span>在算法题中，尝试多使用 TypeScript 进行规范化编码。</span>
                               </li>
                            </ul>
                         </div>
                      </div>

                      <div className="mt-8 pt-6 border-t border-slate-200/60 flex gap-4">
                         <button className="flex-1 py-3 rounded-xl bg-slate-900 text-white font-medium hover:bg-slate-800 transition-colors flex items-center justify-center gap-2 shadow-lg shadow-slate-900/10">
                            <Share2 className="w-4 h-4" />
                            Export Report
                         </button>
                         <button 
                            onClick={() => { setAppState("setup"); setQuestionIndex(0); setIsConfigOpen(false); }}
                            className="flex-1 py-3 rounded-xl bg-white border border-slate-200 text-slate-700 font-medium hover:bg-slate-50 transition-colors flex items-center justify-center gap-2"
                         >
                            <RefreshCw className="w-4 h-4" />
                            New Interview
                         </button>
                      </div>
                   </div>
                </div>
                </div>

            </main>
         </div>
      )}

      <style>{`
        @keyframes blob {
          0% { transform: translate(0px, 0px) scale(1); }
          33% { transform: translate(30px, -50px) scale(1.1); }
          66% { transform: translate(-20px, 20px) scale(0.9); }
          100% { transform: translate(0px, 0px) scale(1); }
        }
        .animate-blob {
          animation: blob 7s infinite;
        }
        .animation-delay-2000 {
          animation-delay: 2s;
        }
        .animation-delay-4000 {
          animation-delay: 4s;
        }
        @keyframes shine {
            100% { transform: translateX(100%) skewX(-12deg); }
        }
        .animate-shine {
            animation: shine 1.5s;
        }
        @keyframes fade-in-up {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .animate-fade-in-up {
            animation: fade-in-up 0.8s ease-out forwards;
        }
        .custom-scrollbar::-webkit-scrollbar {
          width: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: #cbd5e1;
          border-radius: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: #94a3b8;
        }
      `}</style>
    </div>
  );
}
