import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';
import { Button } from './ui/button';
import { Plus, X } from 'lucide-react';

interface IncrementalTopicrefMapsConfigProps {
  recipe: {
    pool_size?: number;
    map_topicref_counts?: number[];
    pretty_print?: boolean;
    deep_folders?: boolean;
  };
  onChange: (recipe: any) => void;
}

export function IncrementalTopicrefMapsConfig({ recipe, onChange }: IncrementalTopicrefMapsConfigProps) {
  // Ensure we always have valid defaults
  const poolSize = recipe?.pool_size ?? 10000;
  const mapCounts = recipe?.map_topicref_counts && recipe.map_topicref_counts.length > 0 
    ? recipe.map_topicref_counts 
    : [10, 100, 1000, 5000, 10000];

  const addMapCount = () => {
    // Always get current values from recipe prop to ensure we have the latest state
    const currentCounts = recipe?.map_topicref_counts || mapCounts;
    const currentPoolSize = recipe?.pool_size || poolSize;
    
    let newCount: number;
    if (currentCounts.length === 0) {
      newCount = 10;
    } else {
      // Find the next logical increment
      const lastCount = currentCounts[currentCounts.length - 1];
      // Try doubling, but if that exceeds pool size, use pool size
      newCount = Math.min(lastCount * 2, currentPoolSize);
      // If doubling would exceed pool size, try adding 1000 or use pool size
      if (newCount === lastCount && lastCount < currentPoolSize) {
        newCount = Math.min(lastCount + 1000, currentPoolSize);
      }
      // Ensure at least 10
      newCount = Math.max(newCount, 10);
    }
    
    const updatedCounts = [...currentCounts, newCount];
    const updatedRecipe = {
      type: 'incremental_topicref_maps',
      pool_size: currentPoolSize,
      map_topicref_counts: updatedCounts,
      pretty_print: recipe?.pretty_print ?? true,
      deep_folders: recipe?.deep_folders ?? false,
    };
    
    onChange(updatedRecipe);
  };

  const removeMapCount = (index: number) => {
    const currentCounts = recipe?.map_topicref_counts || mapCounts;
    const updatedCounts = currentCounts.filter((_, i) => i !== index);
    onChange({
      type: 'incremental_topicref_maps',
      pool_size: recipe?.pool_size ?? poolSize,
      map_topicref_counts: updatedCounts,
      pretty_print: recipe?.pretty_print ?? true,
      deep_folders: recipe?.deep_folders ?? false,
    });
  };

  const updateMapCount = (index: number, value: number) => {
    const currentCounts = recipe?.map_topicref_counts || mapCounts;
    const currentPoolSize = recipe?.pool_size || poolSize;
    const newCounts = [...currentCounts];
    newCounts[index] = Math.min(Math.max(1, value), currentPoolSize);
    onChange({
      type: 'incremental_topicref_maps',
      pool_size: currentPoolSize,
      map_topicref_counts: newCounts,
      pretty_print: recipe?.pretty_print ?? true,
      deep_folders: recipe?.deep_folders ?? false,
    });
  };

  return (
    <div className="space-y-6">
      {/* Description */}
      <div className="p-4 bg-blue-50/50 rounded-lg border border-blue-200/50">
        <h3 className="text-sm font-semibold text-slate-900 mb-2">What You'll Get</h3>
        <ul className="text-sm text-slate-700 space-y-1 list-disc list-inside">
          <li>A pool of <strong>{poolSize.toLocaleString()}</strong> DITA topic files</li>
          <li><strong>{mapCounts.length}</strong> DITA map files with incremental topicref counts</li>
          <li>Each map references topics from the shared pool</li>
          <li>Perfect for testing map parsing performance at different scales</li>
          <li>Useful for benchmarking AEM Guides performance with varying map sizes</li>
        </ul>
      </div>

      {/* Pool Size */}
      <div>
        <Label htmlFor="pool_size">Topic Pool Size</Label>
        <Input
          id="pool_size"
          type="number"
          value={poolSize}
          onChange={(e) => {
            const newPoolSize = parseInt(e.target.value) || 10000;
            const currentCounts = recipe?.map_topicref_counts || mapCounts;
            onChange({
              type: 'incremental_topicref_maps',
              pool_size: newPoolSize,
              map_topicref_counts: currentCounts.map(count => Math.min(count, newPoolSize)),
              pretty_print: recipe?.pretty_print ?? true,
              deep_folders: recipe?.deep_folders ?? false,
            });
          }}
          min={1}
          max={100000}
          step={100}
        />
        <p className="text-sm text-gray-500 mt-1">
          Total number of topics to generate in the pool. Must be &ge; maximum topicref count in maps below.
        </p>
      </div>

      {/* Map Topicref Counts */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <Label>Map Topicref Counts</Label>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              addMapCount();
            }}
            className="h-7 px-2"
          >
            <Plus className="w-3 h-3 mr-1" />
            Add Map
          </Button>
        </div>
        <p className="text-sm text-gray-500 mb-3">
          Configure how many topicrefs each map should have. Each map will reference topics from the pool above.
        </p>
        <div className="space-y-2">
          {mapCounts.map((count, index) => (
            <div key={`map-count-${index}-${count}`} className="flex items-center gap-2">
              <Input
                type="number"
                value={count}
                onChange={(e) => updateMapCount(index, parseInt(e.target.value) || 1)}
                min={1}
                max={poolSize}
                step={10}
                className="flex-1"
              />
              <span className="text-sm text-gray-500 w-20">
                topicrefs
              </span>
              {mapCounts.length > 1 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    removeMapCount(index);
                  }}
                  className="h-8 w-8 p-0 text-red-500 hover:text-red-700 hover:bg-red-50"
                >
                  <X className="w-4 h-4" />
                </Button>
              )}
            </div>
          ))}
        </div>
        {mapCounts.length === 0 && (
          <p className="text-sm text-amber-600 mt-2">
            At least one map is required. Click "Add Map" to add one.
          </p>
        )}
        {mapCounts.length > 0 && Math.max(...mapCounts) > poolSize && (
          <p className="text-sm text-red-600 mt-2">
            Maximum topicref count ({Math.max(...mapCounts)}) exceeds pool size ({poolSize}). 
            Increase pool size or decrease topicref counts.
          </p>
        )}
      </div>

      {/* Deep Folders */}
      <div className="flex items-center space-x-2">
        <Switch
          id="deep_folders"
          checked={recipe?.deep_folders || false}
          onCheckedChange={(checked) => onChange({
            type: 'incremental_topicref_maps',
            pool_size: recipe?.pool_size ?? poolSize,
            map_topicref_counts: recipe?.map_topicref_counts || mapCounts,
            pretty_print: recipe?.pretty_print ?? true,
            deep_folders: checked,
          })}
        />
        <Label htmlFor="deep_folders">Use Deep Folder Structure</Label>
      </div>
      <p className="text-sm text-gray-500 -mt-4">
        Organize topics in nested folders (level1/level2/level3) instead of flat structure
      </p>

      {/* Pretty Print */}
      <div className="flex items-center space-x-2">
        <Switch
          id="pretty_print"
          checked={recipe?.pretty_print !== false}
          onCheckedChange={(checked) => onChange({
            type: 'incremental_topicref_maps',
            pool_size: recipe?.pool_size ?? poolSize,
            map_topicref_counts: recipe?.map_topicref_counts || mapCounts,
            pretty_print: checked,
            deep_folders: recipe?.deep_folders ?? false,
          })}
        />
        <Label htmlFor="pretty_print">Pretty Print XML</Label>
      </div>
      <p className="text-sm text-gray-500 -mt-4">
        Format XML output with indentation for readability
      </p>
    </div>
  );
}
