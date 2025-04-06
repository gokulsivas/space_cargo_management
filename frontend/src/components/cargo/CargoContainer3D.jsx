import React, { useState, useEffect } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";

// Sample Container Data
const sampleContainers = [
  {
    containerId: "container1",
    zone: "zone1",
    width: 4,
    depth: 3,
    height: 6,
  },
  {
    containerId: "container2",
    zone: "zone2",
    width: 5,
    depth: 4,
    height: 7,
  },
];

// Sample Item Data
const sampleItems = [
  {
    itemId: "item1",
    name: "Item 1",
    width: 2,
    depth: 2,
    height: 2,
    priority: 1,
    expiryDate: "2025-12-31",
    usageLimit: 10,
    preferredZone: "zone1",
  },
  {
    itemId: "item2",
    name: "Item 2",
    width: 1,
    depth: 1,
    height: 1,
    priority: 2,
    expiryDate: "2025-06-30",
    usageLimit: 5,
    preferredZone: "zone2",
  },
];

/* 
API Response Structure:
{
  "success": true,
  "placements": [
    {
      "itemId": "item1",
      "containerId": "container1",
      "position": {
        "startCoordinates": { "width": 1, "depth": 1, "height": 0 },
        "endCoordinates": { "width": 3, "depth": 3, "height": 2 }
      }
    },
    {
      "itemId": "item2",
      "containerId": "container2",
      "position": {
        "startCoordinates": { "width": 0, "depth": 0, "height": 0 },
        "endCoordinates": { "width": 1, "depth": 1, "height": 1 }
      }
    }
  ]
}
*/



const CargoContainer3D = () => {
  const [containers, setContainers] = useState(sampleContainers);
  const [items, setItems] = useState(sampleItems);
  const [placements, setPlacements] = useState([]);
  const [selectedContainer, setSelectedContainer] = useState("");
  const [selectedItem, setSelectedItem] = useState("");

  const handlePlaceItem = () => {
    if (!selectedContainer || !selectedItem) return;
  
    const item = items.find((i) => i.itemId === selectedItem);
    if (!item) return;
  
    setPlacements((prev) => [
      ...prev,
      {
        itemId: item.itemId,
        containerId: selectedContainer,
        position: { center: [0, 0, 0], dimensions: item },
      },
    ]);
  };
  
  // Fetch placements from API (Mock for now)
  useEffect(() => {
    const fetchPlacements = async () => {
      // Simulated API response
      const apiResponse = {
        success: true,
        placements: [
          {
            itemId: "item1",
            containerId: "container1",
            position: {
              startCoordinates: { width: 1, depth: 1, height: 0 },
              endCoordinates: { width: 3, depth: 3, height: 2 },
            },
          },
          {
            itemId: "item2",
            containerId: "container2",
            position: {
              startCoordinates: { width: 0, depth: 0, height: 0 },
              endCoordinates: { width: 1, depth: 1, height: 1 },
            },
          },
        ],
      };

      if (apiResponse.success) {
        setPlacements(apiResponse.placements);
      }
    };

    fetchPlacements();
  }, []);

  return (
    <div className="p-8 flex flex-col items-center">
      <div className="w-full max-w-lg space-y-6">
        <div>
          <label className="block text-xl font-semibold text-gray-700 mb-2">
            Select Container
          </label>
          <select
            className="w-full p-3 rounded-md shadow-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
            onChange={(e) => setSelectedContainer(e.target.value)}
          >
            <option value="">Select Container</option>
            {containers.map((container) => (
              <option key={container.containerId} value={container.containerId}>
                {container.containerId}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xl font-semibold text-gray-700 mb-2">
            Select Item
          </label>
          <select
            className="w-full p-3 rounded-md shadow-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
            onChange={(e) => setSelectedItem(e.target.value)}
          >
            <option value="">Select Item</option>
            {items.map((item) => (
              <option key={item.itemId} value={item.itemId}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
      </div>

          <div>
          <button
            onClick={handlePlaceItem}
            className="w-full my-3 py-3 px-6 bg-blue-600 text-white font-semibold rounded-lg shadow-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all"
          >
            Place Item
          </button>
        </div>

      <div className="mt-8 border-2 border-gray-400 rounded-lg shadow-lg overflow-hidden">
        <Canvas style={{ width: "70vw", height: "400px" }} camera={{ position: [20, 20, 40], fov: 50 }}>
          <ambientLight intensity={0.5} />
          <directionalLight position={[5, 5, 5]} />
          <OrbitControls />

          {containers.map((container, index) => (
            <group key={container.containerId} position={[index * 8, 0, 0]}>
              <Container3D position={[0, 0, 0]} dimensions={container} />
              {placements
                .filter((placement) => placement.containerId === container.containerId)
                .map((placement) => (
                  <Item3D
                    key={placement.itemId}
                    position={[
                      placement.position.startCoordinates.width,
                      placement.position.startCoordinates.height,
                      placement.position.startCoordinates.depth,
                    ]}
                    dimensions={items.find((item) => item.itemId === placement.itemId)}
                  />
                ))}
            </group>
          ))}
        </Canvas>
      </div>
    </div>
  );
};

const Item3D = ({ position, dimensions }) => {
  if (!dimensions) return null;
  const { width, height, depth } = dimensions;
  return (
    <mesh position={position}>
      <boxGeometry args={[width, height, depth]} />
      <meshStandardMaterial color="red" />
    </mesh>
  );
};

const Container3D = ({ position, dimensions }) => {
  const { width, height, depth } = dimensions;
  return (
    <group position={position}>
      <mesh position={[-width / 2, height / 2, 0]}>
        <boxGeometry args={[0.1, height, depth]} />
        <meshStandardMaterial color="orange" />
      </mesh>
      <mesh position={[width / 2, height / 2, 0]}>
        <boxGeometry args={[0.1, height, depth]} />
        <meshStandardMaterial color="orange" />
      </mesh>
      <mesh position={[0, 0.05, 0]}>
        <boxGeometry args={[width, 0.1, depth]} />
        <meshStandardMaterial color="orange" />
      </mesh>
      <mesh position={[0, height / 2, -depth / 2]}>
        <boxGeometry args={[width, height, 0.1]} />
        <meshStandardMaterial color="orange" />
      </mesh>
      <mesh position={[0, height, 0]}>
        <boxGeometry args={[width, 0.1, depth]} />
        <meshStandardMaterial color="orange" />
      </mesh>
    </group>
  );
};

export default CargoContainer3D;
