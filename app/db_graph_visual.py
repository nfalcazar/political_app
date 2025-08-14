from pyvis.network import Network
import pandas as pd
from sqlalchemy import create_engine, text
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def create_graph_visualizer(
    db_url: Optional[str] = None,
    output_file: str = "graph.html",
    height: str = "750px",
    width: str = "100%",
    notebook: bool = False,
    limit: Optional[int] = None
):
    """
    Create a graph visualization of the edges in the database.
    
    Args:
        db_url: Database connection URL. If None, will try to get from environment.
        output_file: Name of the HTML file to save the visualization.
        height: Height of the visualization.
        width: Width of the visualization.
        notebook: Whether to run in notebook mode.
    """
    
    # Get database connection
    if db_url is None:
        db_url = os.getenv('SQL_URL', 'postgresql://localhost/political_app')
    
    engine = create_engine(db_url)
    
    # Load edge data
    query = """
    SELECT 
        src_type, 
        src_id, 
        dest_type, 
        dest_id, 
        relationship_type,
        metadata_
    FROM edges
    """
    
    if limit:
        query += f" LIMIT {limit}"
    
    edges_df = pd.read_sql(query, engine)
    
    # Color scheme for different node types
    node_colors = {
        'claim': '#96ceb4',      # Green
        'canonical_claim': '#4ecdc4', # Teal
        'source': '#ff6b6b',       # Red
        'facts': '#45b7d1'        # Blue (fallback)
    }
    
    # Get all unique node IDs and their types
    all_nodes = set()
    for _, row in edges_df.iterrows():
        all_nodes.add((row['src_id'], row['src_type']))
        all_nodes.add((row['dest_id'], row['dest_type']))
    
    # Get unique node types for debugging
    unique_types = set(node_type for _, node_type in all_nodes)
    
    # Fetch content for each node type
    node_contents = {}
    
    # Fetch claims content
    claims_ids = [node_id for node_id, node_type in all_nodes if node_type == 'claim']
    if claims_ids:
        claims_query = f"""
        SELECT id, text FROM claims 
        WHERE id IN ({','.join([f"'{id}'" for id in claims_ids])})
        """
        claims_df = pd.read_sql(claims_query, engine)
        for _, row in claims_df.iterrows():
            node_contents[row['id']] = row['text']
    
    # Fetch canonical_claims content
    canonical_claims_ids = [node_id for node_id, node_type in all_nodes if node_type == 'canonical_claim']
    if canonical_claims_ids:
        canonical_claims_query = f"""
        SELECT id, contents FROM canon_claims 
        WHERE id IN ({','.join([f"'{id}'" for id in canonical_claims_ids])})
        """
        canonical_claims_df = pd.read_sql(canonical_claims_query, engine)
        
        for _, row in canonical_claims_df.iterrows():
            # Convert UUID to string for matching
            node_id = str(row['id'])
            node_contents[node_id] = row['contents']
    
    # Fetch sources content
    sources_ids = [node_id for node_id, node_type in all_nodes if node_type == 'source']
    if sources_ids:
        sources_query = f"""
        SELECT id, link FROM sources 
        WHERE id IN ({','.join([f"'{id}'" for id in sources_ids])})
        """
        sources_df = pd.read_sql(sources_query, engine)
        for _, row in sources_df.iterrows():
            node_contents[row['id']] = row['link']
    
    print(f"Loaded content for {len(node_contents)} nodes")
    
    if edges_df.empty:
        print("No edges found in the database.")
        return
    
    print(f"Found {len(edges_df)} edges to visualize.")
    
    # Create network
    net = Network(
        notebook=notebook, 
        height="100vh", 
        width="100%", 
        directed=True,
        bgcolor="#ffffff",
        font_color="#000000"
    )
    
    # Track added nodes to avoid duplicates
    added_nodes = set()
    
    # Add nodes and edges
    for _, row in edges_df.iterrows():
        # Create node labels
        src_label = f"{row['src_type']}: {row['src_id'][:8]}..."
        dest_label = f"{row['dest_type']}: {row['dest_id'][:8]}..."
        
        # Add source node if not already added
        if row['src_id'] not in added_nodes:
            content = node_contents.get(row['src_id'], 'No content available')
            # Truncate content for tooltip (HTML tooltips have limits)
            content_preview = content[:200] + "..." if len(content) > 200 else content
            node_color = node_colors.get(row['src_type'], '#cccccc')
            net.add_node(
                row['src_id'], 
                label=src_label,
                color=node_color,
                title=f"Type: {row['src_type']}\nID: {row['src_id']}\n\nContent:\n{content_preview}"
            )
            added_nodes.add(row['src_id'])
        
        # Add destination node if not already added
        if row['dest_id'] not in added_nodes:
            content = node_contents.get(row['dest_id'], 'No content available')
            # Truncate content for tooltip (HTML tooltips have limits)
            content_preview = content[:200] + "..." if len(content) > 200 else content
            node_color = node_colors.get(row['dest_type'], '#cccccc')
            net.add_node(
                row['dest_id'], 
                label=dest_label,
                color=node_color,
                title=f"Type: {row['dest_type']}\nID: {row['dest_id']}\n\nContent:\n{content_preview}"
            )
            added_nodes.add(row['dest_id'])
        
        # Add edge
        net.add_edge(
            row['src_id'], 
            row['dest_id'], 
            title=row['relationship_type'],
            arrows='to',
            color='#666666'
        )
    
    # Configure physics for better layout
    net.set_options("""
    var options = {
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -50,
          "centralGravity": 0.01,
          "springLength": 100,
          "springConstant": 0.08
        },
        "maxVelocity": 50,
        "minVelocity": 0.1,
        "solver": "forceAtlas2Based",
        "timestep": 0.35
      }
    }
    """)
    
    # Save the visualization
    try:
        net.show(output_file)
        print(f"Graph visualization saved to {output_file}")
    except AttributeError as e:
        if "'NoneType' object has no attribute 'render'" in str(e):
            # Fallback method for template issues
            print("Using fallback method due to template rendering issue...")
            net.write_html(output_file, notebook=False)
            print(f"Graph visualization saved to {output_file}")
        else:
            raise e
    
    return net

def visualize_sample_data(limit: int = 50):
    """
    Visualize a sample of the data for quick testing.
    
    Args:
        limit: Maximum number of edges to visualize.
    """
    create_graph_visualizer(
        output_file=f"sample_graph_{limit}.html",
        height="600px",
        limit=limit
    )

if __name__ == "__main__":
    # Create visualization
    create_graph_visualizer()
    
    # Also create a sample visualization with limited data
    #visualize_sample_data(20)
