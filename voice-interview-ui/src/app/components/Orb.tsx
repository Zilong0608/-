import React from "react";
import { motion } from "motion/react";

export const Orb = ({ isActive = true, intensity = 1 }: { isActive?: boolean; intensity?: number }) => {
  return (
    <div className="relative flex items-center justify-center w-80 h-80">
      {/* 1. Core Atmosphere (Blue-Purple) */}
      <motion.div
        animate={
          isActive
            ? {
                scale: [1, 1.2 * intensity, 1],
                opacity: [0.4, 0.7, 0.4],
                rotate: [0, 45, 0]
              }
            : { scale: 1, opacity: 0.3, rotate: 0 }
        }
        transition={{
          duration: 4,
          repeat: Infinity,
          ease: "easeInOut",
        }}
        className="absolute inset-0 bg-gradient-to-r from-indigo-500 via-purple-500 to-blue-500 rounded-full blur-3xl opacity-50 mix-blend-screen"
      />
      
      {/* 2. Fluid Blobs (The "Irregular" part) */}
      {isActive && (
        <>
          {/* Blob 1: Pink/Orange - Fast & erratic */}
          <motion.div
            animate={{
              x: [-30, 40, -20, 30, -30],
              y: [-20, 30, -40, 10, -20],
              scale: [0.8, 1.3, 0.9, 1.2, 0.8],
              rotate: [0, 180, 360],
            }}
            transition={{
              duration: 8 / intensity,
              repeat: Infinity,
              ease: "easeInOut",
            }}
            className="absolute w-56 h-56 bg-gradient-to-br from-pink-400 to-rose-400 rounded-full blur-2xl opacity-60 mix-blend-screen top-0 left-10"
          />

          {/* Blob 2: Cyan/Blue - Slow & Deep */}
          <motion.div
            animate={{
              x: [30, -40, 20, -30, 30],
              y: [20, -30, 40, -10, 20],
              scale: [1, 0.7, 1.1, 0.8, 1],
            }}
            transition={{
              duration: 10 / intensity,
              repeat: Infinity,
              ease: "easeInOut",
              delay: 1,
            }}
            className="absolute w-64 h-64 bg-gradient-to-br from-cyan-400 to-blue-600 rounded-full blur-2xl opacity-50 mix-blend-screen bottom-0 right-10"
          />

          {/* Blob 3: White/Bright Core - Pulse */}
          <motion.div
            animate={{
              scale: [0.5, 1.5, 0.5],
              opacity: [0.2, 0.5, 0.2],
            }}
            transition={{
              duration: 3 / intensity,
              repeat: Infinity,
              ease: "easeInOut",
            }}
            className="absolute w-40 h-40 bg-white rounded-full blur-xl mix-blend-overlay"
          />
        </>
      )}

      {/* 3. Static Core (Always visible) */}
      <div className={`relative z-10 w-32 h-32 rounded-full shadow-[inset_0_0_40px_rgba(255,255,255,0.8)] backdrop-blur-md border border-white/40 flex items-center justify-center transition-all duration-700 ${isActive ? 'bg-white/20' : 'bg-white/10'}`}>
         <div className={`w-24 h-24 rounded-full bg-white transition-opacity duration-500 ${isActive ? 'opacity-90 shadow-[0_0_50px_rgba(255,255,255,0.8)]' : 'opacity-40'}`} />
      </div>
      
      {/* 4. Ripple Rings */}
      {isActive && (
          <motion.div
            initial={{ opacity: 0, scale: 0.5 }}
            animate={{ opacity: [0, 0.5, 0], scale: 2.5 }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeOut" }}
            className="absolute z-0 w-full h-full border border-white/30 rounded-full"
          />
      )}
    </div>
  );
};
