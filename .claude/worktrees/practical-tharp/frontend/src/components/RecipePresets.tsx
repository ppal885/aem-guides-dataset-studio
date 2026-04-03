import { useState, useEffect } from 'react';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Sparkles, Zap, TrendingUp, Layers } from 'lucide-react';

interface Preset {
  id: string;
  name: string;
  description: string;
}

interface RecipePresetsProps {
  onSelectPreset: (presetId: string) => void;
}

const presetIcons = [Sparkles, Zap, TrendingUp, Layers];

export function RecipePresets({ onSelectPreset }: RecipePresetsProps) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/v1/presets')
      .then(res => {
        if (!res.ok) throw new Error('Failed to load presets');
        return res.json();
      })
      .then(data => {
        setPresets(data.presets || []);
        setLoading(false);
      })
      .catch(err => {
        console.error('Failed to load presets:', err);
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="text-center py-8">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <p className="mt-2 text-slate-500">Loading presets...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-8 p-4 bg-red-50 border border-red-200 rounded-lg">
        <p className="text-red-600 font-semibold">Error loading presets</p>
        <p className="text-sm text-red-500 mt-1">{error}</p>
      </div>
    );
  }

  if (presets.length === 0) {
    return (
      <div className="text-center py-8 p-6 bg-slate-50 rounded-lg border border-dashed border-slate-300">
        <Sparkles className="w-10 h-10 text-slate-400 mx-auto mb-2" />
        <p className="text-slate-600 font-medium">No presets available</p>
        <p className="text-sm text-slate-500 mt-1">Configure a recipe manually below</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {presets.map((preset, index) => {
        const Icon = presetIcons[index % presetIcons.length];
        return (
          <Card 
            key={preset.id} 
            className="group cursor-pointer hover:shadow-md transition-all border border-slate-200 hover:border-blue-300 bg-white"
            onClick={() => onSelectPreset(preset.id)}
          >
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <CardTitle className="text-base font-semibold text-slate-900 group-hover:text-blue-600 transition-colors">
                    {preset.name}
                  </CardTitle>
                  <CardDescription className="text-sm text-slate-600 mt-1">
                    {preset.description}
                  </CardDescription>
                </div>
                <div className="ml-4 p-2 bg-slate-100 rounded-lg group-hover:bg-blue-50 transition-colors">
                  <Icon className="w-4 h-4 text-slate-600 group-hover:text-blue-600" />
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <Button
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectPreset(preset.id);
                }}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium shadow-sm hover:shadow transition-all"
              >
                <Zap className="w-4 h-4 mr-2" />
                Use This Preset
              </Button>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
