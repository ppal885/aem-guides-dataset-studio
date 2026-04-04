import { RecipeLibrary } from '@/components/RecipeLibrary';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

/**
 * Recipe Library Page
 * 
 * This page allows users to:
 * - Browse saved recipes
 * - Save new recipes
 * - Share recipes publicly
 * - Use recipes in dataset generation
 */
export function RecipeLibraryPage() {
  const handleSelectRecipe = async (recipeId: string) => {
    try {
      const response = await fetch(`/api/v1/recipes/${recipeId}`);
      if (response.ok) {
        const recipe = await response.json();
        
        // Navigate to builder with recipe loaded
        // This would typically use your routing system
        console.log('Loading recipe:', recipe);
        
        // Example: Redirect to builder with recipe config
        // navigate(`/builder?recipe=${recipeId}`);
      }
    } catch (error) {
      console.error('Failed to load recipe:', error);
    }
  };

  const handleSaveRecipe = async (
    name: string,
    description: string,
    recipeConfig: any,
    isPublic: boolean,
    tags: string[]
  ) => {
    try {
      const response = await fetch('/api/v1/recipes/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          description,
          recipe_config: recipeConfig,
          is_public: isPublic,
          tags,
        }),
      });

      if (response.ok) {
        const result = await response.json();
        alert(`Recipe "${result.name}" saved successfully!`);
        // Reload recipes
        window.location.reload();
      } else {
        const error = await response.json();
        alert(`Failed to save recipe: ${error.detail}`);
      }
    } catch (error) {
      console.error('Failed to save recipe:', error);
      alert('Failed to save recipe');
    }
  };

  return (
    <div className="container mx-auto p-6">
      <Card>
        <CardHeader>
          <CardTitle>Recipe Library</CardTitle>
        </CardHeader>
        <CardContent>
          <RecipeLibrary
            onSelectRecipe={handleSelectRecipe}
            onSaveRecipe={handleSaveRecipe}
          />
        </CardContent>
      </Card>
    </div>
  );
}

export default RecipeLibraryPage;
