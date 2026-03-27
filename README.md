<div align="center">

# Interstellar

**Top 10 Finalist - National Space Hackathon 2025**
Jointly organized by IIT Delhi and ISRO | 17th April 2025

A 3D cargo placement and retrieval optimization system for space station inventory management.

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>
<img width="2653" height="1566" alt="image" src="https://github.com/user-attachments/assets/7f102e0a-1fc0-42f5-a277-6be18c980401" />

---

## Overview

Interstellar is a cargo management system built to solve the problem of optimal 3D space utilization in constrained environments such as space station modules, warehouses, and cargo containers. It places, retrieves, searches, and disposes of items intelligently - using advanced algorithms that account for item priority, accessibility, group dependencies, and physical feasibility.

The project was developed as a team submission for the **National Space Hackathon 2025**, organized jointly by **IIT Delhi** and **ISRO**, where team Interstellar secured a spot among the **top 10 finalist teams** nationally.

<!-- PLACEHOLDER: Add your certificate image here -->
<!-- ![Certificate](assets/certificate.png) -->

---

## Problem Statement

The challenge involves optimal space utilization in constrained 3D environments like space station stowage modules. Specifically:

- Packing 3D cuboidal objects into a bounded cuboidal container
- Considering item priority levels, accessibility, and rotational flexibility
- Respecting group-based dependencies between related objects
- Ensuring high-priority items remain easily retrievable
- Handling expired or used-up item disposal with structured return manifests
- Maintaining physical feasibility - no overlaps, full containment

The objective is to maximize space utilization while preserving item accessibility and handling all operational constraints.

---

## System Pages

### Home Dashboard
<img width="3813" height="1885" alt="image" src="https://github.com/user-attachments/assets/4beb6102-26b6-45cb-9fb4-88a89010daf8" />


The main control panel displaying container state, active items, utilization metrics, and quick-access actions.

---

### 3D Visualization
<img width="3757" height="2051" alt="image" src="https://github.com/user-attachments/assets/b2b028d2-9bf8-41a4-b5f4-d20804c1d1dd" />

An interactive 3D view of the cargo container showing item placements, zone boundaries, and spatial occupancy in real time.

---

### Item Retrieval Page
<img width="3721" height="2064" alt="image" src="https://github.com/user-attachments/assets/472adf7a-a1b7-4cfd-8534-88a7a473da85" />


Provides step-by-step retrieval instructions for a requested item, including obstructions to clear and the optimal path computed by the A* algorithm.

---

### Time Simulation Page
<img width="3524" height="1654" alt="image" src="https://github.com/user-attachments/assets/785bba1d-e478-4209-b566-759a77bf73a7" />


Simulates the passage of time within the container - tracking item expiry, usage depletion, and triggering waste identification and return manifest generation.

---

<img width="3696" height="2109" alt="image" src="https://github.com/user-attachments/assets/f7604309-a332-4df3-bd78-acaba08cec6e" />
<img width="3561" height="1416" alt="image" src="https://github.com/user-attachments/assets/6c216292-be46-4b12-8841-5013b0170c89" />
<img width="3255" height="1399" alt="image" src="https://github.com/user-attachments/assets/7217f56e-aa99-4ee6-93df-47c5afda86e0" />



---

## Key Features

- Advanced 3D bin packing using Octree spatial partitioning and SparseMatrix collision detection
- Priority-aware A* pathfinding for optimal item retrieval
- Dependency graph-based item search and grouping
- Greedy waste selection and structured return manifest generation
- Interactive 3D visualization of cargo layout
- Time simulation for expiry and usage-based waste tracking
- Dockerized deployment - runs anywhere with a single command

---

## Algorithms

### placement_algo.py - AdvancedCargoPlacement

Handles placement of incoming items using an **Octree** for efficient spatial partitioning and a **SparseMatrix** for collision detection. Considers item priority, preferred zones, dimensions, and rotational flexibility.

### retrieve_algo.py - PriorityAStarRetrieval

Computes the optimal retrieval path for a requested item using **A\* pathfinding**. Accounts for obstructing items, the number of steps to clear them, and item priority to minimize retrieval cost.

### search_algo.py - ItemSearchSystem

Locates items within the container using a **Dependency Graph** that models relationships between stored objects. Supports search by item ID, name, or zone while accounting for groupings and constraints.

### waste_algo.py - Greedy Selection + Return Manifests

Identifies expired or used-up items using a greedy selection strategy. Generates structured return manifests with step-by-step instructions for removing and routing waste items out of the container.

---

## Tech Stack

| Component        | Technology                          |
|------------------|-------------------------------------|
| Language         | Python 3.8+                         |
| Backend          | FastAPI                             |
| Containerization | Docker                              |
| Spatial Index    | Octree, SparseMatrix                |
| Pathfinding      | A* Search                           |
| Dependency Model | Directed Graph                      |
| Package Manager  | pip                                 |

---

## Project Structure

```
space_cargo_management/
├── placement_algo.py         # AdvancedCargoPlacement — Octree + SparseMatrix
├── retrieve_algo.py          # PriorityAStarRetrieval — A* pathfinding
├── search_algo.py            # ItemSearchSystem — Dependency graph search
├── waste_algo.py             # Greedy waste selection + return manifests
├── app/                      # FastAPI application and route handlers
├── config/                   # Configuration files
├── uploads/                  # Uploaded item/container data
├── Dockerfile                # Docker image definition
├── requirements.txt          # Python dependencies
├── package.json              # Node dependencies
└── README.md
```

---

## Prerequisites

- Python 3.8+
- Docker
- pip
- Git

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/gokulsivas/space_cargo_management.git
cd space_cargo_management
```

### 2. Docker Setup (Recommended)

Build the image:

```bash
docker build -t space-cargo-management .
```

Run the container:

```bash
docker run --network=host space-cargo-management
```

### 3. Local Setup (Without Docker)

```bash
pip install -r requirements.txt
# PLACEHOLDER: Replace with your actual entry point
python main.py
```

---

## Contributing

Contributions are welcome. To get started:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "Add your feature"`
4. Push and open a Pull Request

---

## Hackathon Recognition

This project was built for the **National Space Hackathon 2025**, jointly organized by **IIT Delhi** and **ISRO** on 17th April 2025. Team Interstellar secured a position among the **Top 10 Finalist Teams** nationally.

![ISRO_IITD_Interstellar](https://github.com/user-attachments/assets/26da9543-6668-48c6-a1ff-9ce0979acd81)


---

## Team

| Name       | GitHub                                          |
|------------|-------------------------------------------------|
| Gokul S    | [@gokulsivas](https://github.com/gokulsivas)    |
| Ajay Anand | <!-- PLACEHOLDER: Add GitHub link -->           |
| Raghav K   | [@Tusker13-04](https://github.com/Tusker13-04) |

---

## License

This project is licensed under the [MIT License](LICENSE).
