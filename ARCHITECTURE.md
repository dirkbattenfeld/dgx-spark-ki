# Architecture & Infrastructure Overview

`dgx-spark-ki` is designed as a modular, local AI cloud platform. Cloning the repository and executing the Ansible deployment provisions a complete, containerized service stack tailored for high-performance retrieval and inference.

## 1. Core Stack Components

By running the deployment playbooks, the following external and supporting components are orchestrated alongside the core application:

* **vLLM:** High-throughput and memory-efficient inference engine for serving local large language models.
* **Infinity:** High-performance embedding server optimized for generating dense vector representations (e.g., using BGE models).
* **Qdrant:** Vector database utilized for high-speed similarity search and vector storage within the RAG pipeline.
* **Docling:** Document conversion and parsing engine for ingesting complex file formats (PDFs, Office docs, etc.).
* **PostgreSQL:** Relational database for persistent application state and relational data management.
* **Redis:** In-memory data store acting as a message broker for event streams and state caching.
* **Garage S3:** Lightweight, distributed S3-compatible object storage for document access in the network during ingestion.

## 2. Quick Setup Guide

To deploy the platform locally using the provided automation workflows, follow these core configuration steps:

### Step 1: Prerequisites

Before cloning the repository and executing the deployment, ensure that the following core tools are installed and available in your system's PATH:

* **Make:** Used to trigger deployment targets and automation commands via the Makefile.
* **Docker:** Required for container runtime management and executing container checks.
* **Ansible:** Used for provisioning and executing the infrastructure automation playbooks.

### Step 2: Configure Environment & Templates
* Review and adjust the configuration files, paths, IPs and network ports in the Ansible template files to match your environment in dgx-spark-ki/ansible/group_vars.
* Insert necessary external credentials and tokens (e.g., your Hugging Face token for restricted model downloads) or security in production.

### Step 3: Core Control via Makefile

The project provides a unified `Makefile` in the root directory to handle all deployment and remote orchestration tasks via Ansible.

* **`make up gx10 MODE=request`**
  provisions all needed microservices to run the RAG application on the PC and (remotely) on the DGX spark.
* **`make`** (or **`make help`**)
  Displays an auto-generated overview of all available commands and options.
* **What happens during execution:**
  1. Base container images are pulled or built locally.
  2. Custom application images are compiled.
  3. Microservices, databases, and inference engines are provisioned and started in the correct topological order.

### Step 4: Access the Application
* Once all containers are running healthily, open your browser and access the interactive user interface:
  * **Chainlit GUI:** `http://localhost:<your-configured-port>`
