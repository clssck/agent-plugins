import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";

export function CommandMenu() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey && e.key === "k") setOpen((o) => !o);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="palette"
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.96 }}
          transition={{ duration: 0.25 }}
        >
          <input placeholder="Type a command" />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
