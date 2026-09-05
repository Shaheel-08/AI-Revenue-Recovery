# RecoverOS — 5-Minute Buildathon Demo Script

This document provides a step-by-step guide for presenting RecoverOS in a 5-minute video for the Razorpay AI Buildathon.

## 0:00 - 0:30 | Introduction & The Problem
*Screen: Show the RecoverOS Dashboard (Revenue Radar)*
**Voiceover**: "Hi, I'm Shaheel, and this is RecoverOS for the Razorpay AI Revenue Recovery track. The problem today is that when a payment fails, merchants use brute-force fixed retries. It's expensive, causes customer fatigue, and often fails because the retry strategy doesn't match the root cause. RecoverOS solves this by turning recovery into an economic optimization problem."

## 0:30 - 1:15 | The Dashboard & Flagship Demo Trigger
*Screen: Scroll through Dashboard (Top Causes, Trend Chart)*
**Voiceover**: "Here is our command center. We track revenue at risk and top failure causes. Let's run a live recovery scenario by clicking 'Run Flagship Demo'."
*Action: Click [🚀 RUN FLAGSHIP DEMO] on Dashboard*
*Screen: Navigates automatically to the Transaction Intelligence page for Rahul.*

## 1:15 - 2:30 | Transaction Intelligence & AI Analysis
*Screen: Transaction Intelligence page (Status: Failed)*
**Voiceover**: "We have a ₹4,999 failure from Rahul. Instead of a blind retry, I'll hit 'Run AI Analysis'."
*Action: Click [⚡ RUN AI ANALYSIS]*
*Screen: Watch the pipeline animate (Retrieving -> Root Cause -> Economics)*
**Voiceover**: "Notice what just happened. The AI diagnosed the root cause as a Hard Card Decline. It pulled Rahul's history—he has a high LTV but this specific card keeps failing. Then, it simulated all candidate strategies. You can see the 'What-If' table here. Retrying now has a 10% chance. Sending a WhatsApp payment link has an 85% chance. The AI calculates the Expected Net Revenue, subtracting communication costs, and recommends WhatsApp."

## 2:30 - 3:15 | Safety, Policy, and Execution
*Screen: Click [Execute WhatsApp Nudge]*
**Voiceover**: "Before execution, the AI's recommendation passes through our deterministic Policy Engine. If this were a suspected fraud case, or if it was 11 PM during Quiet Hours, the system physically blocks execution. It passed, so we execute."
*Screen: Show status change to Recovered, switch to Approvals Page*
**Voiceover**: "But what about high-value B2B transactions? For amounts over our threshold, the system routes them here to the Human Approval Queue, keeping the merchant in control of high-stakes recovery."

## 3:15 - 4:15 | Batch Evaluation Lab
*Screen: Navigate to the Evaluate Page*
*Action: Click [▶ RUN SYNTHETIC BENCHMARK]*
**Voiceover**: "To prove this works at scale, we built an Evaluation Lab. We're running a synthetic benchmark of 2,000 transactions, pitting RecoverOS against a standard 'retry every 24 hours' baseline."
*Screen: Show benchmark results (Lift in Revenue, Drop in Messages)*
**Voiceover**: "The results are clear. RecoverOS recovers more revenue while sending fewer messages, reducing customer fatigue. We also have strict idempotency—notice the duplicate charge rate is zero."

## 4:15 - 5:00 | Conclusion & Settings
*Screen: Navigate to Settings page, show Policy controls*
**Voiceover**: "Merchants have full control over the circuit breakers here in the Policy Center. Finally, behind the scenes, a Contextual Bandit learning agent updates its weights after every outcome, meaning RecoverOS gets smarter the longer you use it. Thank you for watching!"
