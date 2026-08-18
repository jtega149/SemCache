import express from "express";
import openaiChatCompletions from "../controllers/openai_controller.ts";

const router = express.Router();

router.post("/v1/chat/completions", openaiChatCompletions);

export default router;
