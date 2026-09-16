# dgx-spark-ki

A local AI cloud platform designed for networks of Linux PCs and DGX Spark hardware (as well as licensed equivalent systems from other manufacturers). By adapting Dockerfiles and model configurations, the repository also fully supports standard Linux PCs equipped with NVIDIA GPUs.

## Overview

`dgx-spark-ki` provides a unified, on-premise infrastructure for executing and orchestrating local AI workloads. At the application layer, it features a Retrieval-Augmented Generation (RAG) system utilizing **Chainlit** for the interactive user interface and **NiceGUI** for context management.

## Key Features

* **Local Cloud Architecture:** Seamlessly coordinates AI workloads across mixed local hardware nodes (Linux PCs and hardware accelerators).
* **Flexible Hardware Support:** Out-of-the-box configurations optimized for dgx spark, with straightforward paths for standard NVIDIA GPU setups.
* **Interactive RAG Application:** Production-ready implementation featuring real-time chat interfaces and dynamic context handling.
* **Modular Infrastructure:** Built on containerized components for straightforward deployment and scaling.

## Architecture & Deployment

For a detailed breakdown of the microservice stack (including vLLM, Qdrant, Redis, and Garage S3) and a step-by-step setup guide for the Ansible deployment, please refer to our [Architecture Documentation](ARCHITECTURE.md).

## License

This project is distributed under the terms of the [GNU Affero General Public License v3.0](LICENSE).
