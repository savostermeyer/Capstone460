const express = require("express");
const { MongoClient } = require("mongodb");
const multer = require("multer");
const path = require("path");
const { GoogleGenerativeAI } = require("@google/generative-ai");
const bcrypt = require("bcrypt");
require("dotenv").config();

const app = express();
const port = process.env.PORT || 3000;

// Initialize Gemini AI
const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
const model = genAI.getGenerativeModel({
  model: process.env.GEMINI_MODEL || "gemini-2.0-flash",
});

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static("front-end"));

// MongoDB connection
const client = new MongoClient(process.env.MONGODB_URI, {
  serverSelectionTimeoutMS: 5000,
});
let db;

async function connectDB() {
  try {
    await client.connect();
    db = client.db("skin-images");
    console.log("Connected to MongoDB");
  } catch (error) {
    console.error("MongoDB connection error:", error);
    process.exit(1);
  }
}

// Get auth database helper
function getAuthDB() {
  return client.db("auth");
}

// Configure multer for file uploads
const storage = multer.memoryStorage();
const upload = multer({
  storage: storage,
  limits: { fileSize: 10 * 1024 * 1024 }, // 10MB limit
  fileFilter: (req, file, cb) => {
    const filetypes = /jpeg|jpg|png/;
    const mimetype = filetypes.test(file.mimetype);
    const extname = filetypes.test(
      path.extname(file.originalname).toLowerCase(),
    );

    if (mimetype && extname) {
      return cb(null, true);
    }
    cb(new Error("Only image files (jpeg, jpg, png) are allowed"));
  },
});

// Routes
// Health check endpoint to verify DB connection
app.get("/api/health", async (req, res) => {
  try {
    await client.db().admin().ping();
    res.json({
      status: "healthy",
      message: "Database connected successfully",
      database: "skin-images",
    });
  } catch (error) {
    res.status(503).json({
      status: "unhealthy",
      message: "Database connection failed",
      error: error.message,
    });
  }
});

app.post("/api/upload", upload.single("image"), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No image file provided" });
    }

    const imageDocument = {
      filename: req.file.originalname,
      contentType: req.file.mimetype,
      size: req.file.size,
      data: req.file.buffer,
      uploadDate: new Date(),
      patientInfo: req.body.patientInfo || {},
    };

    const result = await db.collection("images").insertOne(imageDocument);

    res.status(201).json({
      message: "Image uploaded successfully",
      imageId: result.insertedId,
    });
  } catch (error) {
    console.error("Upload error:", error);
    res.status(500).json({ error: "Failed to upload image" });
  }
});

app.get("/api/images/:id", async (req, res) => {
  try {
    const { ObjectId } = require("mongodb");
    const image = await db.collection("images").findOne({
      _id: new ObjectId(req.params.id),
    });

    if (!image) {
      return res.status(404).json({ error: "Image not found" });
    }

    res.set("Content-Type", image.contentType);
    res.send(image.data.buffer);
  } catch (error) {
    console.error("Error retrieving image:", error);
    res.status(500).json({ error: "Failed to retrieve image" });
  }
});

// Authentication routes
// Register endpoint
app.post("/api/auth/register", async (req, res) => {
  try {
    const { email, password } = req.body;

    if (!email || !password) {
      return res.status(400).json({ error: "Email and password are required" });
    }

    if (password.length < 6) {
      return res
        .status(400)
        .json({ error: "Password must be at least 6 characters" });
    }

    const authDB = getAuthDB();
    const usersCollection = authDB.collection("users");

    // Check if user already exists
    const existingUser = await usersCollection.findOne({
      email: email.toLowerCase(),
    });
    if (existingUser) {
      return res.status(409).json({ error: "User already exists" });
    }

    // Hash password
    const hashedPassword = await bcrypt.hash(password, 10);

    // Create user
    const newUser = {
      email: email.toLowerCase(),
      password: hashedPassword,
      createdAt: new Date(),
    };

    const result = await usersCollection.insertOne(newUser);

    res.status(201).json({
      message: "User created successfully",
      userId: result.insertedId,
      email: email.toLowerCase(),
    });
  } catch (error) {
    console.error("Registration error:", error);
    res.status(500).json({ error: "Failed to create user" });
  }
});

// Login endpoint
app.post("/api/auth/login", async (req, res) => {
  try {
    const { email, password } = req.body;

    if (!email || !password) {
      return res.status(400).json({ error: "Email and password are required" });
    }

    const authDB = getAuthDB();
    const usersCollection = authDB.collection("users");

    // Find user
    const user = await usersCollection.findOne({ email: email.toLowerCase() });
    if (!user) {
      return res.status(401).json({ error: "Invalid email or password" });
    }

    // Verify password
    const isValidPassword = await bcrypt.compare(password, user.password);
    if (!isValidPassword) {
      return res.status(401).json({ error: "Invalid email or password" });
    }

    // Update last login
    await usersCollection.updateOne(
      { _id: user._id },
      { $set: { lastLogin: new Date() } },
    );

    res.json({
      message: "Login successful",
      email: user.email,
    });
  } catch (error) {
    console.error("Login error:", error);
    res.status(500).json({ error: "Failed to login" });
  }
});

// Chatbot endpoint
app.post("/chat", async (req, res) => {
  try {
    const userMessage = req.body.text || "";

    if (!userMessage) {
      return res.status(400).json({ reply: "Please provide a message." });
    }

    // Create context for skin lesion assistant
    const prompt = `You are SkinAI Assistant, a helpful AI assistant for a skin lesion classification system. 
You help users understand skin conditions, answer questions about the upload process, and provide general dermatology information.
You should be professional, empathetic, and remind users that this is not a substitute for professional medical advice.

User question: ${userMessage}

Provide a helpful, concise response:`;

    const result = await model.generateContent(prompt);
    const response = await result.response;
    const reply = response.text();

    res.json({ reply });
  } catch (error) {
    console.error("Chat error:", error);
    res.status(500).json({
      reply: "I'm having trouble connecting right now. Please try again later.",
    });
  }
});

// Start server
connectDB().then(() => {
  app.listen(port, () => {
    console.log(`Server running on http://localhost:${port}`);
  });
});

// Graceful shutdown
process.on("SIGINT", async () => {
  await client.close();
  console.log("MongoDB connection closed");
  process.exit(0);
});
