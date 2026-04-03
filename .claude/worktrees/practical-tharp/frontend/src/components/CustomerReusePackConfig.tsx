import { Input } from './ui/input';
import { Label } from './ui/label';

interface CustomerReusePackConfigProps {
  recipe: {
    remove_map_count?: number;
    shared_topics?: number;
    topic_references_per_map?: number;
    key_definitions?: number;
    key_groups?: number;
    external_references?: number;
  };
  onChange: (recipe: any) => void;
}

export function CustomerReusePackConfig({ recipe, onChange }: CustomerReusePackConfigProps) {
  return (
    <div className="space-y-4">
      <div>
        <Label>Remove Map Count</Label>
        <Input
          type="number"
          value={recipe.remove_map_count || 10}
          onChange={(e) => onChange({ ...recipe, remove_map_count: parseInt(e.target.value) || 10 })}
          min={1}
          max={100}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of maps that reference shared topics
        </p>
      </div>

      <div>
        <Label>Shared Topics</Label>
        <Input
          type="number"
          value={recipe.shared_topics || 500}
          onChange={(e) => onChange({ ...recipe, shared_topics: parseInt(e.target.value) || 500 })}
          min={10}
          max={10000}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of shared topics referenced by maps
        </p>
      </div>

      <div>
        <Label>Topic References per Map</Label>
        <Input
          type="number"
          value={recipe.topic_references_per_map || 100}
          onChange={(e) => onChange({ ...recipe, topic_references_per_map: parseInt(e.target.value) || 100 })}
          min={1}
          max={1000}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of topic references per map
        </p>
      </div>

      <div>
        <Label>Key Definitions</Label>
        <Input
          type="number"
          value={recipe.key_definitions || 200}
          onChange={(e) => onChange({ ...recipe, key_definitions: parseInt(e.target.value) || 200 })}
          min={0}
          max={5000}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of key definitions for content reuse
        </p>
      </div>

      <div>
        <Label>Key Groups</Label>
        <Input
          type="number"
          value={recipe.key_groups || 5}
          onChange={(e) => onChange({ ...recipe, key_groups: parseInt(e.target.value) || 5 })}
          min={0}
          max={50}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of key groups for organized key management
        </p>
      </div>

      <div>
        <Label>External References</Label>
        <Input
          type="number"
          value={recipe.external_references || 10}
          onChange={(e) => onChange({ ...recipe, external_references: parseInt(e.target.value) || 10 })}
          min={0}
          max={100}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of external references per map
        </p>
      </div>
    </div>
  );
}
