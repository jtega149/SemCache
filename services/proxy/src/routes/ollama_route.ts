import express from "express";
import ollamaChat from "../controllers/ollama_controller.ts";

const router = express.Router();

router.post("/api/chat", ollamaChat);

export default router;
