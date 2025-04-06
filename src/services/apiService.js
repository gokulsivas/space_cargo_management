import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// Placement Recommendation API
export const getPlacementRecommendations = async (data) => {
  try {
    const response = await api.post('/placement', {
      items: data.items,
      containers: data.containers
    });

    // Ensure response matches expected format
    return {
      data: {
        success: response.data.success || false,
        placements: response.data.placements || [],
        rearrangements: response.data.rearrangements || []
      }
    };
  } catch (error) {
    console.error('Placement API Error:', error);
    throw error;
  }
};

// Search and Retrieval APIs
export const searchItem = async (params) => {
  const requestParams = {
    ...(params.itemId && { item_id: parseInt(params.itemId) }),
    ...(params.itemName && { name: params.itemName }),
    ...(params.userId && { user_id: params.userId })
  };
  
  try {
    const response = await api.get('/search', { params: requestParams });
    console.log('Search API Response:', response.data);
    return response;
  } catch (error) {
    console.error('Search API Error:', error.response?.data || error);
    throw error;
  }
};

export const retrieveItem = async (data) => {
  return api.post('/retrieve', {
    item_id: data.itemId,
    user_id: data.userId,
    timestamp: data.timestamp
  });
};

export const placeItem = async (data) => {
  return api.post('/place', data);
};

// Waste Management APIs
export const identifyWaste = async () => {
  return api.get('/waste/identify');
};

export const returnWastePlan = async (data) => {
  return api.post('/waste/return-plan', {
    undocking_container_id: data.undockingContainerId,
    undocking_date: data.undockingDate,
    max_weight: data.maxWeight
  });
};

export const completeUndocking = async (data) => {
  return api.post('/waste/complete-undocking', {
    undocking_container_id: data.undockingContainerId,
    timestamp: data.timestamp
  });
};

// Time Simulation API
export const simulateDays = async (simulationParams) => {
  try {
    // Transform the parameters to match backend schema
    const requestBody = {
      numOfDays: simulationParams.numOfDays,
      toTimestamp: simulationParams.toTimestamp,
      itemsToBeUsedPerDay: simulationParams.itemsToBeUsedPerDay.map(item => {
        // Only include item_id or name, not both
        const itemParams = {};
        if (item.itemId) {
          itemParams.item_id = parseInt(item.itemId);
        } else if (item.name) {
          itemParams.name = item.name;
        }
        return itemParams;
      })
    };

    const response = await fetch(`${API_BASE_URL}/simulate/day`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody),
    });
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('API Error:', error);
    throw error;
  }
};

// Import/Export APIs
export const importItems = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  return api.post('/import/items', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  });
};

export const importContainers = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  return api.post('/import/containers', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  });
};

export const exportArrangement = async () => {
  return api.get('/export/arrangement', {
    responseType: 'blob'
  });
};

// Logging API
export const getLogs = async (startDate, endDate, filters = {}) => {
  // Format dates to ISO string with UTC timezone
  const formattedStartDate = new Date(startDate).toISOString();
  const formattedEndDate = new Date(endDate).toISOString();

  // Prepare params object
  const params = {
    startDate: formattedStartDate,
    endDate: formattedEndDate
  };

  // Add filters if they have values
  if (filters.itemId) params.item_id = filters.itemId;
  if (filters.userId) params.user_id = filters.userId;
  if (filters.actionType) params.action_type = filters.actionType;

  return api.get('/logs', { params });
};

export const clearLogs = async () => {
  return api.post('/logs/clear');
};

// Container 3D Visualization APIs
export const updateContainer3D = async (placementData) => {
  try {
    const response = await api.post('/container3d/update', placementData);
    return response.data;
  } catch (error) {
    console.error('Container 3D Update Error:', error);
    throw error;
  }
};

export const getContainer3DData = async () => {
  try {
    const response = await axios.get(`${API_BASE_URL}/container3d/data`);
    if (response.data) {
      return {
        data: {
          dimensions: response.data.dimensions || {
            width: 0,
            height: 0,
            depth: 0
          },
          items: response.data.items || []
        }
      };
    }
    throw new Error('Invalid response format');
  } catch (error) {
    console.error('Error fetching container 3D data:', error);
    throw error;
  }
};

export const getContainerItems = async () => {
  try {
    const response = await api.get('/container/items');
    return response;
  } catch (error) {
    console.error('Error fetching container items:', error);
    throw error;
  }
};
