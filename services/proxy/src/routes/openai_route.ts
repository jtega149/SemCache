import express from "express";
import chatCompletions from "../controllers/openai_controller.ts";

const router = express.Router();

router.post("/chat/completions", chatCompletions);

export default router;
