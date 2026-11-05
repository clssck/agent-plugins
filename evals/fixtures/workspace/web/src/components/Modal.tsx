import { AnimatePresence, motion } from "framer-motion";
import type { ReactNode } from "react";

// Changed in this branch: exit now slides down instead of fading.
export function Modal({ open, children }: { open: boolean; children: ReactNode }) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="modal"
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 200 }}
          transition={{ duration: 0.5, ease: "easeIn" }}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
