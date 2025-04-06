import React, { useState, useEffect } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Box } from '@react-three/drei';
import { getContainerItems } from '../../services/apiService';

const CargoContainer3D = () => {
  const [containers, setContainers] = useState([]);
  const [selectedContainer, setSelectedContainer] = useState('');
  const [containerItems, setContainerItems] = useState([]);
  const [containerDimensions, setContainerDimensions] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await getContainerItems();
        if (response && response.data) {
          const { containers, items, dimensions } = response.data;
          
          setContainers(containers);
          if (containers.length > 0) {
            setSelectedContainer(containers[0]);
            setContainerItems(items[containers[0]] || []);
            setContainerDimensions(dimensions[containers[0]]);
          }
        }
      } catch (err) {
        setError(err.message || 'Failed to fetch container data');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  useEffect(() => {
    if (selectedContainer) {
      const fetchContainerData = async () => {
        try {
          const response = await getContainerItems();
          if (response && response.data) {
            const { items, dimensions } = response.data;
            setContainerItems(items[selectedContainer] || []);
            setContainerDimensions(dimensions[selectedContainer]);
          }
        } catch (err) {
          setError(err.message || 'Failed to fetch container items');
        }
      };

      fetchContainerData();
    }
  }, [selectedContainer]);

  if (loading) return <div className="p-4 text-center">Loading 3D visualization...</div>;
  if (error) return <div className="p-4 text-center text-red-500">Error: {error}</div>;
  if (!containers.length) return <div className="p-4 text-center">No containers available</div>;
  if (!containerDimensions) return <div className="p-4 text-center">No container dimensions available</div>;

  // Calculate camera position based on container dimensions
  const maxDimension = Math.max(
    containerDimensions.width,
    containerDimensions.height,
    containerDimensions.depth
  );
  const cameraDistance = maxDimension * 2;

  // Calculate container center position
  const containerCenter = {
    x: containerDimensions.width / 2,
    y: containerDimensions.height / 2,
    z: containerDimensions.depth / 2
  };

  return (
    <div className="p-4">
      <div className="mb-4">
        <label className="block text-sm font-medium mb-2">Select Container</label>
        <select
          value={selectedContainer}
          onChange={(e) => setSelectedContainer(e.target.value)}
          className="w-full p-2 border rounded"
        >
          {containers.map(containerId => (
            <option key={containerId} value={containerId}>
              Container {containerId}
            </option>
          ))}
        </select>
      </div>

      <div className="mb-4">
        <h3 className="text-sm font-medium">Container Dimensions:</h3>
        <p className="text-sm">
          Width: {containerDimensions.width}cm, 
          Height: {containerDimensions.height}cm, 
          Depth: {containerDimensions.depth}cm
        </p>
      </div>

      <div style={{ width: '100%', height: '600px', border: '1px solid #ccc', borderRadius: '4px' }}>
        <Canvas camera={{ position: [cameraDistance, cameraDistance, cameraDistance], fov: 50 }}>
          <ambientLight intensity={0.5} />
          <pointLight position={[cameraDistance, cameraDistance, cameraDistance]} />
          
          {/* Container */}
          <Box
            args={[
              containerDimensions.width,
              containerDimensions.height,
              containerDimensions.depth
            ]}
            position={[containerCenter.x, containerCenter.y, containerCenter.z]}
          >
            <meshStandardMaterial 
              color="gray" 
              wireframe 
              transparent
              opacity={0.2}
            />
          </Box>

          {/* Items */}
          {containerItems.map((item, index) => {
            // Calculate item dimensions
            const width = item.end_width_cm - item.start_width_cm;
            const height = item.end_height_cm - item.start_height_cm;
            const depth = item.end_depth_cm - item.start_depth_cm;

            // Calculate item position (center point)
            const positionX = (item.start_width_cm + item.end_width_cm) / 2;
            const positionY = (item.start_height_cm + item.end_height_cm) / 2;
            const positionZ = (item.start_depth_cm + item.end_depth_cm) / 2;

            return (
              <Box
                key={item.item_id}
                args={[width, height, depth]}
                position={[positionX, positionY, positionZ]}
              >
                <meshStandardMaterial 
                  color={`hsl(${(index * 137.5) % 360}, 70%, 60%)`}
                  transparent
                  opacity={0.8}
                />
              </Box>
            );
          })}

          <OrbitControls 
            enablePan={true}
            enableZoom={true}
            enableRotate={true}
          />
          <gridHelper args={[maxDimension * 2, 20]} />
          <axesHelper args={[maxDimension]} />
        </Canvas>
      </div>
    </div>
  );
};

export default CargoContainer3D;
