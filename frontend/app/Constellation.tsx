"use client";

import { useEffect, useRef } from "react";

/**
 * Animated constellation background: points drift slowly and draw lines to
 * nearby neighbours, forming a shifting web of polygons. Sized to its parent,
 * DPR-aware, and honours prefers-reduced-motion (renders a single static frame).
 */
export function Constellation({ dark }: { dark: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const darkRef = useRef(dark);
  useEffect(() => { darkRef.current = dark; }, [dark]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const parent = canvas?.parentElement;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !parent || !ctx) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const MAX_DIST = 140;

    let width = 0;
    let height = 0;
    let pts: { x: number; y: number; vx: number; vy: number }[] = [];

    function seed() {
      width = parent!.clientWidth;
      height = parent!.clientHeight;
      canvas!.width = width * dpr;
      canvas!.height = height * dpr;
      canvas!.style.width = `${width}px`;
      canvas!.style.height = `${height}px`;
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.max(24, Math.min(70, Math.round((width * height) / 17000)));
      pts = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.28,
        vy: (Math.random() - 0.5) * 0.28,
      }));
    }

    function draw() {
      const d = darkRef.current;
      const line = d ? "129,140,248" : "220,38,38";
      const dot = d ? "165,180,252" : "220,38,38";
      ctx!.clearRect(0, 0, width, height);

      // connecting lines (alpha fades with distance)
      for (let i = 0; i < pts.length; i++) {
        for (let j = i + 1; j < pts.length; j++) {
          const dx = pts[i].x - pts[j].x;
          const dy = pts[i].y - pts[j].y;
          const dist = Math.hypot(dx, dy);
          if (dist < MAX_DIST) {
            ctx!.strokeStyle = `rgba(${line},${(1 - dist / MAX_DIST) * 0.26})`;
            ctx!.lineWidth = 1;
            ctx!.beginPath();
            ctx!.moveTo(pts[i].x, pts[i].y);
            ctx!.lineTo(pts[j].x, pts[j].y);
            ctx!.stroke();
          }
        }
      }
      // nodes
      ctx!.fillStyle = `rgba(${dot},0.35)`;
      for (const p of pts) {
        ctx!.beginPath();
        ctx!.arc(p.x, p.y, 1.6, 0, Math.PI * 2);
        ctx!.fill();
      }
    }

    let raf = 0;
    function frame() {
      for (const p of pts) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0 || p.x > width) p.vx *= -1;
        if (p.y < 0 || p.y > height) p.vy *= -1;
      }
      draw();
      raf = requestAnimationFrame(frame);
    }

    seed();
    if (reduce) {
      draw();
    } else {
      raf = requestAnimationFrame(frame);
    }

    const onResize = () => seed();
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  return <canvas ref={canvasRef} aria-hidden className="absolute inset-0 h-full w-full" />;
}
