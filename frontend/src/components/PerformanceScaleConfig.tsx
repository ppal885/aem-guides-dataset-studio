import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

interface PerformanceScaleConfigProps {
  recipe: {
    topic_count?: number;
    batch_size?: number;
    depth?: number;
    children_per_level?: number;
    root_topics?: number;
    children_per_root?: number;
    include_maps?: boolean;
    pretty_print?: boolean;
  };
  onChange: (recipe: any) => void;
  recipeType: 'large_scale' | 'deep_hierarchy' | 'wide_branching';
}

export function PerformanceScaleConfig({ recipe, onChange, recipeType }: PerformanceScaleConfigProps) {
  if (recipeType === 'large_scale') {
    return (
      <div className="space-y-4">
        <div>
          <Label>Topic Count</Label>
          <Input
            type="number"
            value={recipe.topic_count || 100000}
            onChange={(e) => onChange({ ...recipe, topic_count: parseInt(e.target.value) || 100000 })}
            min={1000}
            max={1000000}
          />
          <p className="text-sm text-gray-500 mt-1">
            Number of topics to generate (100k+ for large scale testing)
          </p>
        </div>

        <div>
          <Label>Batch Size</Label>
          <Input
            type="number"
            value={recipe.batch_size || 1000}
            onChange={(e) => onChange({ ...recipe, batch_size: parseInt(e.target.value) || 1000 })}
            min={100}
            max={10000}
          />
          <p className="text-sm text-gray-500 mt-1">
            Number of topics to generate per batch
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <Switch
            id="pretty-print"
            checked={recipe.pretty_print !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, pretty_print: checked })}
          />
          <Label htmlFor="pretty-print">Pretty Print XML</Label>
        </div>
      </div>
    );
  }

  if (recipeType === 'deep_hierarchy') {
    return (
      <div className="space-y-4">
        <div>
          <Label>Depth</Label>
          <Input
            type="number"
            value={recipe.depth || 10}
            onChange={(e) => onChange({ ...recipe, depth: parseInt(e.target.value) || 10 })}
            min={5}
            max={20}
          />
          <p className="text-sm text-gray-500 mt-1">
            Number of nesting levels (10+ for deep hierarchy)
          </p>
        </div>

        <div>
          <Label>Children per Level</Label>
          <Input
            type="number"
            value={recipe.children_per_level || 5}
            onChange={(e) => onChange({ ...recipe, children_per_level: parseInt(e.target.value) || 5 })}
            min={2}
            max={20}
          />
          <p className="text-sm text-gray-500 mt-1">
            Number of children at each level
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <Switch
            id="include-maps"
            checked={recipe.include_maps !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, include_maps: checked })}
          />
          <Label htmlFor="include-maps">Include Maps</Label>
        </div>

        <div className="flex items-center space-x-2">
          <Switch
            id="pretty-print"
            checked={recipe.pretty_print !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, pretty_print: checked })}
          />
          <Label htmlFor="pretty-print">Pretty Print XML</Label>
        </div>
      </div>
    );
  }

  if (recipeType === 'wide_branching') {
    return (
      <div className="space-y-4">
        <div>
          <Label>Root Topics</Label>
          <Input
            type="number"
            value={recipe.root_topics || 2}
            onChange={(e) => onChange({ ...recipe, root_topics: parseInt(e.target.value) || 2 })}
            min={1}
            max={10}
          />
          <p className="text-sm text-gray-500 mt-1">
            Number of root topics
          </p>
        </div>

        <div>
          <Label>Children per Root</Label>
          <Input
            type="number"
            value={recipe.children_per_root || 1000}
            onChange={(e) => onChange({ ...recipe, children_per_root: parseInt(e.target.value) || 1000 })}
            min={100}
            max={5000}
          />
          <p className="text-sm text-gray-500 mt-1">
            Number of children per root topic (1000+ for wide branching)
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <Switch
            id="include-maps"
            checked={recipe.include_maps !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, include_maps: checked })}
          />
          <Label htmlFor="include-maps">Include Maps</Label>
        </div>

        <div className="flex items-center space-x-2">
          <Switch
            id="pretty-print"
            checked={recipe.pretty_print !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, pretty_print: checked })}
          />
          <Label htmlFor="pretty-print">Pretty Print XML</Label>
        </div>
      </div>
    );
  }

  return null;
}
