# PI Camera

A Raspberry Pi night vision motion camera with Telegram alerts and Dropbox upload.

## What it does

- Detects motion using OpenCV MOG2 background subtraction with day/night threshold switching
- Captures a snapshot when motion is detected
- Sends the snapshot instantly to a **Telegram** chat via Bot API
- Records a video clip of the motion event
- Uploads the finished clip to **Dropbox** and sends the share link via Telegram

## Hardware

- Raspberry Pi 4
- Arducam 5MP OV5647 Camera Module with IR LED (CSI interface)

## Quick start

See the [GitHub repository](https://github.com/GeoffVanHornTest/Pi_Camera-1) for setup instructions.

## Project analysis

A three-plan independent analysis of the codebase — what works, what doesn't, and the prioritised fix order.

[View the Three-Plan Analysis](plan-compare.html)

## False trigger investigation

Diagnostic analysis of motion false triggers using an 8-script analysis suite. Includes confirmed false trigger deep-dive (08:15–08:50 empty-room window), failure mode breakdown, and scoring fix recommendations.

[View the False Trigger Analysis](false-trigger-analysis.html)
