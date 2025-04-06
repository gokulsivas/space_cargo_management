import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api'; // Adjust based on your backend

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// Placement Recommendation API
export const getPlacementRecommendations = async (data) => {
  return api.post('/placement', data);
};

// Search and Retrieval APIs
export const searchItem = async (params) => {
  return api.get('/search', { params });
};

export const retrieveItem = async (data) => {
  return api.post('/retrieve', data);
};

export const placeItem = async (data) => {
  return api.post('/place', data);
};

// Waste Management APIs
export const identifyWaste = async () => {
  return api.get('/waste/identify');
};

export const returnWastePlan = async (data) => {
  return api.post('/waste/return-plan', data);
};

export const completeUndocking = async (data) => {
  return api.post('/waste/complete-undocking', data);
};

// Time Simulation API
export const simulateDays = async (data) => {
  return api.post('/simulate/day', data);
};

// Import/Export APIs
export const importItems = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  return api.post('/import/items', formData);
};

export const importContainers = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  return api.post('/import/containers', formData);
};

export const exportArrangement = async () => {
  return api.get('/export/arrangement', { responseType: 'blob' });
};

// Logging API
export const getLogs = async (params) => {
  return api.get('/logs', { params });
};
