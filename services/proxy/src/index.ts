import express from "express";
import dotenv from "dotenv";
import cors from 'cors';
import openaiRoute from "./routes/openai_route.ts";

dotenv.config();

const PORT = process.env.PORT || 8001;
const app = express();
app.use(cors());
app.use(express.json());

app.use("/v1", openaiRoute);

app.listen(PORT, () => {
    console.log(`Proxy server is running on port ${PORT}`);
})


