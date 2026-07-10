# PI Camera

A Raspberry Pi night vision motion camera with automated Gmail alerts.

## What it does

- Detects motion using OpenCV background subtraction
- Captures a snapshot when motion is detected
- Sends an email alert with the snapshot attached via Gmail SMTP
- Records a video clip of the motion event

## Hardware

- Raspberry Pi 4
- Arducam 5MP OV5647 Camera Module with IR LED (CSI interface)

## Quick start

See the [GitHub repository](https://github.com/GeoffVanHornTest/Pi_Camera-1) for setup instructions.

## Project analysis

A three-plan independent analysis of the codebase — what works, what doesn't, and the prioritised fix order.

[View the Three-Plan Analysis](plan-compare.html)
