import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';
import { Button } from './ui/button';
import { Plus, X } from 'lucide-react';

interface InsuranceIncrementalConfigProps {
  recipe: {
    max_topics?: number;
    map_sizes?: number[];
    include_local_dtd_stubs?: boolean;
    output_root_folder_name?: string;
  };
  onChange: (recipe: any) => void;
}

export function InsuranceIncrementalConfig({ recipe, onChange }: InsuranceIncrementalConfigProps) {
  const maxTopics = recipe?.max_topics ?? 10000;
  const mapSizes = recipe?.map_sizes && recipe.map_sizes.length > 0 
    ? recipe.map_sizes 
    : [10, 100, 1000, 5000, 10000];
  const includeDtdStubs = recipe?.include_local_dtd_stubs !== false;
  const outputRootFolder = recipe?.output_root_folder_name || "aem_guides_insurance_incremental";

  const addMapSize = () => {
    const currentSizes = recipe?.map_sizes || mapSizes;
    const currentMaxTopics = recipe?.max_topics || maxTopics;
    
    let newSize: number;
    if (currentSizes.length === 0) {
      newSize = 10;
    } else {
      const lastSize = currentSizes[currentSizes.length - 1];
      if (lastSize < 100) {
        newSize = Math.min(lastSize * 10, currentMaxTopics);
      } else if (lastSize < 1000) {
        newSize = Math.min(lastSize * 10, currentMaxTopics);
      } else {
        newSize = Math.min(lastSize + 1000, currentMaxTopics);
      }
      newSize = Math.max(newSize, 10);
    }
    
    const updatedSizes = [...currentSizes, newSize].sort((a, b) => a - b);
    onChange({
      type: 'insurance_incremental',
      max_topics: currentMaxTopics,
      map_sizes: updatedSizes,
      include_local_dtd_stubs: includeDtdStubs,
      output_root_folder_name: outputRootFolder,
    });
  };

  const removeMapSize = (index: number) => {
    const currentSizes = recipe?.map_sizes || mapSizes;
    const updatedSizes = currentSizes.filter((_, i) => i !== index);
    onChange({
      type: 'insurance_incremental',
      max_topics: recipe?.max_topics || maxTopics,
      map_sizes: updatedSizes,
      include_local_dtd_stubs: includeDtdStubs,
      output_root_folder_name: outputRootFolder,
    });
  };

  const updateMapSize = (index: number, value: number) => {
    const currentSizes = recipe?.map_sizes || mapSizes;
    const currentMaxTopics = recipe?.max_topics || maxTopics;
    const newSizes = [...currentSizes];
    newSizes[index] = Math.min(Math.max(10, value), currentMaxTopics);
    // Sort to maintain increasing order
    newSizes.sort((a, b) => a - b);
    onChange({
      type: 'insurance_incremental',
      max_topics: currentMaxTopics,
      map_sizes: newSizes,
      include_local_dtd_stubs: includeDtdStubs,
      output_root_folder_name: outputRootFolder,
    });
  };

  return (
    <div className="space-y-6">
      {/* Description */}
      <div className="p-4 bg-blue-50/50 rounded-lg border border-blue-200/50">
        <h3 className="text-sm font-semibold text-slate-900 mb-2">What You'll Get</h3>
        <ul className="text-sm text-slate-700 space-y-1 list-disc list-inside">
          <li><strong>{maxTopics.toLocaleString()}</strong> insurance domain DITA topic files</li>
          <li><strong>{mapSizes.length}</strong> DITA map files with incremental topicref counts</li>
          <li>Insurance-specific content: policies, claims, underwriting, compliance</li>
          <li>Rotating themes: Term Life, Health, Motor, Endorsements, Surveyor Notes</li>
          <li>Each topic includes simpletable and codeblock elements</li>
          {includeDtdStubs && <li>DTD stub files in technicalContent/dtd/</li>}
        </ul>
      </div>

      {/* Max Topics */}
      <div>
        <Label htmlFor="max_topics">Maximum Topics</Label>
        <Input
          id="max_topics"
          type="number"
          value={maxTopics}
          onChange={(e) => {
            const newMaxTopics = parseInt(e.target.value) || 10000;
            const currentSizes = recipe?.map_sizes || mapSizes;
            const adjustedSizes = currentSizes.map(size => Math.min(size, newMaxTopics));
            onChange({
              type: 'insurance_incremental',
              max_topics: newMaxTopics,
              map_sizes: adjustedSizes,
              include_local_dtd_stubs: includeDtdStubs,
              output_root_folder_name: outputRootFolder,
            });
          }}
          min={10}
          max={50000}
          step={100}
        />
        <p className="text-sm text-gray-500 mt-1">
          Total number of insurance topics to generate. Must be &ge; maximum map size below.
        </p>
      </div>

      {/* Map Sizes */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <Label>Map Sizes (Topicref Counts)</Label>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              addMapSize();
            }}
            className="h-7 px-2"
          >
            <Plus className="w-3 h-3 mr-1" />
            Add Map Size
          </Button>
        </div>
        <p className="text-sm text-gray-500 mb-3">
          Configure topicref counts for each map. Each map will reference topics from the pool above.
        </p>
        <div className="space-y-2">
          {mapSizes.map((size, index) => (
            <div key={`map-size-${index}-${size}`} className="flex items-center gap-2">
              <Input
                type="number"
                value={size}
                onChange={(e) => updateMapSize(index, parseInt(e.target.value) || 10)}
                min={10}
                max={maxTopics}
                step={10}
                className="flex-1"
              />
              <span className="text-sm text-gray-500 w-20">
                topicrefs
              </span>
              {mapSizes.length > 1 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    removeMapSize(index);
                  }}
                  className="h-8 w-8 p-0 text-red-500 hover:text-red-700 hover:bg-red-50"
                >
                  <X className="w-4 h-4" />
                </Button>
              )}
            </div>
          ))}
        </div>
        {mapSizes.length === 0 && (
          <p className="text-sm text-amber-600 mt-2">
            At least one map size is required. Click "Add Map Size" to add one.
          </p>
        )}
        {mapSizes.length > 0 && Math.max(...mapSizes) > maxTopics && (
          <p className="text-sm text-red-600 mt-2">
            Maximum map size ({Math.max(...mapSizes)}) exceeds max topics ({maxTopics}). 
            Increase max topics or decrease map sizes.
          </p>
        )}
        {mapSizes.length > 1 && mapSizes.some((size, idx) => idx > 0 && size <= mapSizes[idx - 1]) && (
          <p className="text-sm text-amber-600 mt-2">
            Map sizes must be in increasing order.
          </p>
        )}
      </div>

      {/* Output Root Folder */}
      <div>
        <Label htmlFor="output_root_folder_name">Output Root Folder Name</Label>
        <Input
          id="output_root_folder_name"
          type="text"
          value={outputRootFolder}
          onChange={(e) => onChange({
            type: 'insurance_incremental',
            max_topics: recipe?.max_topics || maxTopics,
            map_sizes: recipe?.map_sizes || mapSizes,
            include_local_dtd_stubs: includeDtdStubs,
            output_root_folder_name: e.target.value || "aem_guides_insurance_incremental",
          })}
          placeholder="aem_guides_insurance_incremental"
        />
        <p className="text-sm text-gray-500 mt-1">
          Root folder name for generated dataset files.
        </p>
      </div>

      {/* Include DTD Stubs */}
      <div className="flex items-center space-x-2">
        <Switch
          id="include_local_dtd_stubs"
          checked={includeDtdStubs}
          onCheckedChange={(checked) => onChange({
            type: 'insurance_incremental',
            max_topics: recipe?.max_topics || maxTopics,
            map_sizes: recipe?.map_sizes || mapSizes,
            include_local_dtd_stubs: checked,
            output_root_folder_name: outputRootFolder,
          })}
        />
        <Label htmlFor="include_local_dtd_stubs">Include Local DTD Stubs</Label>
      </div>
      <p className="text-sm text-gray-500 -mt-4">
        Generate technicalContent/dtd/topic.dtd and map.dtd as minimal stubs
      </p>
    </div>
  );
}
