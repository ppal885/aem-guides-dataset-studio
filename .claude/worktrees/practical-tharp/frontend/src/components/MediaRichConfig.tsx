import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

interface MediaRichConfigProps {
  recipe: {
    topic_count?: number;
    images_per_topic?: number;
    generate_images?: boolean;
    image_width?: number;
    image_height?: number;
    include_map?: boolean;
    pretty_print?: boolean;
  };
  onChange: (recipe: any) => void;
}

export function MediaRichConfig({ recipe, onChange }: MediaRichConfigProps) {
  return (
    <div className="space-y-4">
      <div>
        <Label>Topic Count</Label>
        <Input
          type="number"
          value={recipe.topic_count || 50}
          onChange={(e) => onChange({ ...recipe, topic_count: parseInt(e.target.value) || 50 })}
          min={10}
          max={5000}
        />
      </div>

      <div>
        <Label>Images per Topic</Label>
        <Input
          type="number"
          value={recipe.images_per_topic || 3}
          onChange={(e) => onChange({ ...recipe, images_per_topic: parseInt(e.target.value) || 3 })}
          min={0}
          max={20}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of images to include in each topic
        </p>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="generate-images"
          checked={recipe.generate_images !== false}
          onCheckedChange={(checked) => onChange({ ...recipe, generate_images: checked })}
        />
        <Label htmlFor="generate-images">Generate Placeholder Images</Label>
      </div>

      {recipe.generate_images !== false && (
        <>
          <div>
            <Label>Image Width (px)</Label>
            <Input
              type="number"
              value={recipe.image_width || 800}
              onChange={(e) => onChange({ ...recipe, image_width: parseInt(e.target.value) || 800 })}
              min={100}
              max={4000}
            />
          </div>

          <div>
            <Label>Image Height (px)</Label>
            <Input
              type="number"
              value={recipe.image_height || 600}
              onChange={(e) => onChange({ ...recipe, image_height: parseInt(e.target.value) || 600 })}
              min={100}
              max={4000}
            />
          </div>
        </>
      )}

      <div className="flex items-center space-x-2">
        <Switch
          id="include-map"
          checked={recipe.include_map !== false}
          onCheckedChange={(checked) => onChange({ ...recipe, include_map: checked })}
        />
        <Label htmlFor="include-map">Include Map</Label>
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
